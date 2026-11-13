import argparse
import asyncio
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import webbrowser
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ==========================================
# 1. ENVIRONMENT & DIRECTORY CONFIGURATION
# ==========================================
BASE_DIR = Path(__file__).parent.resolve()
LOG_DIR = BASE_DIR / ".logs"
LOG_DIR.mkdir(exist_ok=True)

env_file = BASE_DIR / ".env"
if env_file.exists():
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in ('"', "'"):
            val = val[1:-1]
        os.environ.setdefault(key, val)
    os.environ["PYTHONIOENCODING"] = "utf-8"
    os.environ["PYTHONUNBUFFERED"] = "1"
    print(f"Loaded environment from {env_file}")
else:
    os.environ["PYTHONIOENCODING"] = "utf-8"
    os.environ["PYTHONUNBUFFERED"] = "1"
    print("Warning: no .env found")

# ==========================================
# 2. RUNTIME CONFIGURATION & CONSTANTS
# ==========================================
# Schema: (Service Name, App Target Path, Local Port, API URL Slug)
SERVICES = [
    ("auth", "src.auth.main:app", 8001, "auth"),
    ("roles", "src.roles.main:app", 8002, "roles"),
    ("employees", "src.employees.main:app", 8003, "employees"),
    ("wallet", "src.wallet.main:app", 8004, "wallets"),
    ("recognition", "src.recognition.main:app", 8005, "recognitions"),
    ("rewards", "src.rewards.main:app", 8006, "rewards"),
    ("organization", "src.organization.main:app", 8007, "organizations"),
    ("analytics", "src.analytics.main:app", 8008, "analytics"),
]

DEFAULT_HEALTH_TIMEOUT = 60
HEALTH_TIMEOUT_OVERRIDES = {"employees": 90}

PO_FLAGS = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0

# Runtime state trackers
SERVICE_STATE: dict[str, dict] = {}
LOG_VIEWER_PROCS: list[subprocess.Popen] = []
INFRA_STATE: dict[str, dict] = {
    "postgres": {"ok": False, "latency_ms": 0.0, "detail": "Not checked"},
    "redis": {"ok": False, "latency_ms": 0.0, "detail": "Not checked"},
}


# ==========================================
# 3. DATABASE & REDIS STABILITY CHECKS
# ==========================================
def _resolve_db_url() -> str:
    for key in ("DATABASE_URL", "POSTGRES_URL", "DB_URL", "SQLALCHEMY_DATABASE_URI"):
        val = os.environ.get(key)
        if val:
            return val
    user = os.environ.get("POSTGRES_USER", "postgres")
    password = os.environ.get("POSTGRES_PASSWORD", "postgres")
    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("POSTGRES_PORT", "5432")
    db = os.environ.get("POSTGRES_DB", "aabhar")
    return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{db}"


def _resolve_redis_url() -> str:
    for key in ("REDIS_URL", "CELERY_BROKER_URL", "CACHE_REDIS_URL"):
        val = os.environ.get(key)
        if val:
            return val
    host = os.environ.get("REDIS_HOST", "localhost")
    port = os.environ.get("REDIS_PORT", "6379")
    db = os.environ.get("REDIS_DB", "0")
    password = os.environ.get("REDIS_PASSWORD", "")
    auth = f":{password}@" if password else ""
    return f"redis://{auth}{host}:{port}/{db}"


async def _async_check_postgres(db_url: str, timeout: float = 5.0) -> tuple[bool, float, str]:
    """Executes a real 'SELECT 1' query against PostgreSQL to verify connection & auth stability."""
    start = time.perf_counter()
    try:
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine

        engine_url = db_url
        if engine_url.startswith("postgres://"):
            engine_url = engine_url.replace("postgres://", "postgresql+asyncpg://", 1)
        elif engine_url.startswith("postgresql://") and "+asyncpg" not in engine_url:
            engine_url = engine_url.replace("postgresql://", "postgresql+asyncpg://", 1)

        engine = create_async_engine(engine_url, pool_pre_ping=True)
        try:
            async with asyncio.timeout(timeout):
                async with engine.connect() as conn:
                    val = (await conn.execute(text("SELECT 1"))).scalar()
                    if val != 1:
                        return False, 0.0, "Unexpected SELECT 1 response"
        finally:
            await engine.dispose()

        elapsed_ms = (time.perf_counter() - start) * 1000
        parsed = urllib.parse.urlparse(engine_url)
        host_info = f"{parsed.hostname or 'localhost'}:{parsed.port or 5432}/{parsed.path.lstrip('/')}"
        return True, elapsed_ms, f"SELECT 1 OK ({host_info})"

    except Exception as exc:
        # Fallback: check if at least TCP socket is reachable or if auth/SQL failed
        elapsed_ms = (time.perf_counter() - start) * 1000
        return False, elapsed_ms, f"{type(exc).__name__}: {str(exc).splitlines()[0][:80]}"


def check_redis_stability(redis_url: str, timeout: float = 4.0) -> tuple[bool, float, str]:
    """Verifies Redis stability via RESP PING -> PONG handshake (and optional AUTH)."""
    parsed = urllib.parse.urlparse(redis_url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 6379
    password = urllib.parse.unquote(parsed.password) if parsed.password else None

    start = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=timeout) as sock:
            sock.settimeout(timeout)
            if password:
                auth_cmd = f"*2\r\n$4\r\nAUTH\r\n${len(password)}\r\n{password}\r\n".encode("utf-8")
                sock.sendall(auth_cmd)
                auth_resp = sock.recv(128).decode("utf-8", errors="replace").strip()
                if not auth_resp.startswith("+OK"):
                    return False, 0.0, f"Redis AUTH failed: {auth_resp}"

            sock.sendall(b"*1\r\n$4\r\nPING\r\n")
            resp = sock.recv(128).decode("utf-8", errors="replace").strip()
            elapsed_ms = (time.perf_counter() - start) * 1000

            if "PONG" in resp:
                return True, elapsed_ms, f"PONG ({host}:{port})"
            return False, elapsed_ms, f"Unexpected Redis response: {resp}"
    except Exception as exc:
        elapsed_ms = (time.perf_counter() - start) * 1000
        return False, elapsed_ms, f"{type(exc).__name__} ({host}:{port}): {exc}"


def verify_infrastructure(retries: int = 3) -> bool:
    """Runs stability checks (with retries) on PostgreSQL and Redis and updates INFRA_STATE."""
    print("\n🔍 Checking Database (PostgreSQL) & Cache (Redis) stability...")
    db_url = _resolve_db_url()
    redis_url = _resolve_redis_url()

    # 1. PostgreSQL Check (with retry for transient startup lag)
    pg_ok, pg_ms, pg_detail = False, 0.0, ""
    for attempt in range(1, retries + 1):
        pg_ok, pg_ms, pg_detail = asyncio.run(_async_check_postgres(db_url))
        if pg_ok:
            break
        if attempt < retries:
            time.sleep(1.0)

    INFRA_STATE["postgres"] = {"ok": pg_ok, "latency_ms": pg_ms, "detail": pg_detail}
    pg_icon = "✓" if pg_ok else "❌"
    print(f" {pg_icon}  PostgreSQL : {'ONLINE' if pg_ok else 'FAILED'} ({pg_ms:.1f} ms) — {pg_detail}")

    # 2. Redis Check (with retry)
    rd_ok, rd_ms, rd_detail = False, 0.0, ""
    for attempt in range(1, retries + 1):
        rd_ok, rd_ms, rd_detail = check_redis_stability(redis_url)
        if rd_ok:
            break
        if attempt < retries:
            time.sleep(1.0)

    INFRA_STATE["redis"] = {"ok": rd_ok, "latency_ms": rd_ms, "detail": rd_detail}
    rd_icon = "✓" if rd_ok else "❌"
    print(f" {rd_icon}  Redis      : {'ONLINE' if rd_ok else 'FAILED'} ({rd_ms:.1f} ms) — {rd_detail}")

    return pg_ok and rd_ok


# ==========================================
# 4. PROCESS, PORT & CACHE CLEANUP UTILITIES
# ==========================================
def clear_pycache() -> None:
    """Removes stale __pycache__ directories inside src/ to prevent stale bytecode issues."""
    src_dir = BASE_DIR / "src"
    if not src_dir.exists():
        return
    removed = 0
    for cache_dir in src_dir.rglob("__pycache__"):
        shutil.rmtree(cache_dir, ignore_errors=True)
        removed += 1
    if removed:
        print(f"🧹 Cleared {removed} __pycache__ directories.")


def kill_port_owners(ports: list[int]) -> None:
    """Finds and terminates any orphaned processes listening on target service ports."""
    if os.name == "nt":
        port_list = ",".join(str(p) for p in ports)
        ps_cmd = (
            f"$ports = @({port_list}); "
            "Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | "
            "Where-Object { $ports -contains $_.LocalPort } | "
            "Select-Object -ExpandProperty OwningProcess -Unique | "
            "ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }"
        )
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_cmd],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    else:
        for port in ports:
            subprocess.run(
                ["fuser", "-k", f"{port}/tcp"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )


# ==========================================
# 5. SERVICE LIFECYCLE & HEALTH CHECKS
# ==========================================
def start_service(name: str, app: str, port: int, slug: str) -> None:
    """Starts a single microservice and redirects its stdout/stderr to a dedicated log file."""
    log_path = LOG_DIR / f"{name}.log"
    log_handle = open(log_path, "w", encoding="utf-8", buffering=1)

    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            app,
            "--host",
            "0.0.0.0",
            "--port",
            str(port),
            "--root-path",
            f"/aabhar/v1/{slug}",
            "--reload",
            "--use-colors",
        ],
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        creationflags=PO_FLAGS,
        env=dict(os.environ),
        cwd=str(BASE_DIR),
    )

    SERVICE_STATE[name] = {
        "name": name,
        "app": app,
        "port": port,
        "slug": slug,
        "proc": proc,
        "log_handle": log_handle,
        "log_path": log_path,
        "healthy": False,
    }


def stop_service(name: str) -> None:
    """Stops a single microservice and its child workers cleanly."""
    info = SERVICE_STATE.get(name)
    if not info:
        return

    proc: subprocess.Popen = info["proc"]
    if proc and proc.poll() is None:
        try:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            else:
                proc.terminate()
                proc.wait(timeout=3)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    log_handle = info.get("log_handle")
    if log_handle and not log_handle.closed:
        try:
            log_handle.close()
        except Exception:
            pass


def wait_for_service(name: str, port: int, timeout: int) -> tuple[str, bool]:
    """Polls /health until 200 OK or timeout."""
    url = f"http://127.0.0.1:{port}/health"
    deadline = time.time() + timeout

    while time.time() < deadline:
        proc = SERVICE_STATE[name]["proc"]
        if proc.poll() is not None:
            print(f" ❌ {name:<15} exited prematurely (code {proc.returncode})", flush=True)
            return name, False

        try:
            with urllib.request.urlopen(url, timeout=1.5) as r:
                if r.status == 200:
                    print(f" ✓  {name:<15} healthy (port {port})", flush=True)
                    return name, True
        except Exception:
            pass
        time.sleep(1)

    print(f" ⚠  {name:<15} health check timed out after {timeout}s", flush=True)
    return name, False


def shutdown_all_services() -> None:
    """Stops all microservices, closes log viewer windows, and frees ports."""
    print("\n🛑 Shutting down all services and log windows...")

    for viewer in LOG_VIEWER_PROCS:
        if viewer.poll() is None:
            try:
                viewer.terminate()
            except Exception:
                pass

    for name in list(SERVICE_STATE.keys()):
        stop_service(name)

    kill_port_owners([port for _, _, port, _ in SERVICES])
    print("✅ All services and orphaned workers stopped.")


# ==========================================
# 6. SEPARATE WINDOW LOG VIEWER
# ==========================================
def open_log_window(name: str) -> None:
    """Opens a new separate console window tailing the specified service's log file."""
    info = SERVICE_STATE.get(name)
    if not info:
        print(f"Unknown service: {name}")
        return

    log_path: Path = info["log_path"]
    port: int = info["port"]
    title = f"Aabhar Logs - {name.upper()} (Port {port})"

    if os.name == "nt":
        ps_path = str(log_path).replace("'", "''")
        ps_cmd = (
            f"$Host.UI.RawUI.WindowTitle = '{title}'; "
            f"Write-Host '=== Live Logs: {name.upper()} (Port {port}) ===' -ForegroundColor Cyan; "
            f"Write-Host 'Log file: {ps_path}' -ForegroundColor DarkGray; "
            f"Write-Host 'Close this window at any time — the service will keep running.`n' -ForegroundColor Yellow; "
            f"Get-Content -Path '{ps_path}' -Wait -Tail 100 -Encoding UTF8"
        )
        viewer = subprocess.Popen(
            ["powershell", "-NoExit", "-NoProfile", "-Command", ps_cmd],
            creationflags=subprocess.CREATE_NEW_CONSOLE,
        )
        LOG_VIEWER_PROCS.append(viewer)
        print(f" 🪟 Opened log window for '{name}' (port {port}).")
    else:
        print(f"Log file located at: {log_path} (run: tail -f {log_path})")


# ==========================================
# 7. INTERACTIVE MENU
# ==========================================
def print_dashboard() -> None:
    pg = INFRA_STATE["postgres"]
    rd = INFRA_STATE["redis"]
    pg_badge = f"🟢 ONLINE ({pg['latency_ms']:.1f}ms)" if pg["ok"] else "🔴 OFFLINE"
    rd_badge = f"🟢 ONLINE ({rd['latency_ms']:.1f}ms)" if rd["ok"] else "🔴 OFFLINE"

    print("\n" + "=" * 72)
    print(" 🎛️  AABHAR MICROSERVICES CONTROL PANEL")
    print("=" * 72)
    print(f" 🗄️  PostgreSQL: {pg_badge:<24} ⚡ Redis: {rd_badge}")
    print("-" * 72)
    print(f" {'#':<4} {'Service':<15} {'Port':<7} {'PID':<9} {'Status':<12} {'Swagger Docs'}")
    print("-" * 72)

    for idx, (name, _, port, slug) in enumerate(SERVICES, start=1):
        info = SERVICE_STATE.get(name, {})
        proc: subprocess.Popen | None = info.get("proc")
        is_running = proc is not None and proc.poll() is None

        if not is_running:
            status_str = "❌ CRASHED"
            pid_str = "-"
        elif info.get("healthy"):
            status_str = "🟢 ONLINE"
            pid_str = str(proc.pid)
        else:
            status_str = "🟡 UNHEALTHY"
            pid_str = str(proc.pid)

        doc_url = f"http://localhost:{port}/aabhar/v1/{slug}/docs"
        print(f" [{idx}]  {name:<15} {port:<7} {pid_str:<9} {status_str:<12} {doc_url}")

    print("-" * 72)
    print(" Commands:")
    print("  • [1-8]    Open live logs for that service in a new window")
    print("  • [a]      Open live log windows for ALL services at once")
    print("  • [r 1-8]  Restart a specific service (e.g., 'r 3' restarts employees)")
    print("  • [i]      Run Database (PostgreSQL) & Redis stability check now")
    print("  • [d 1-8]  Open Swagger docs for a service (or 'd' for all)")
    print("  • [c]      Clear __pycache__ across src/")
    print("  • [s]      Refresh status table")
    print("  • [q]      Stop all services and exit")
    print("=" * 72)


def interactive_loop() -> None:
    print_dashboard()
    while True:
        for name, info in SERVICE_STATE.items():
            proc = info["proc"]
            if proc.poll() is not None and info.get("healthy"):
                info["healthy"] = False
                print(
                    f"\n⚠ Notice: '{name}' exited with code {proc.returncode}. "
                    "Use '1-8' to view its log or 'r <#>' to restart."
                )

        try:
            choice = input(
                "\nSelect option (1-8 logs, a=all logs, r <#>=restart, i=infra check, s=status, q=quit): "
            ).strip().lower()
        except EOFError:
            break

        if not choice:
            continue

        if choice in ("q", "quit", "exit"):
            break

        elif choice in ("s", "status"):
            print_dashboard()

        elif choice in ("i", "infra", "db"):
            verify_infrastructure(retries=1)
            print_dashboard()

        elif choice in ("a", "all"):
            for name, _, _, _ in SERVICES:
                open_log_window(name)

        elif choice in ("c", "cache"):
            clear_pycache()

        elif choice.startswith("d"):
            parts = choice.split()
            if len(parts) == 1:
                for _, _, port, slug in SERVICES:
                    webbrowser.open(f"http://localhost:{port}/aabhar/v1/{slug}/docs")
                print(" 🌐 Opened all Swagger documentation tabs.")
            elif len(parts) == 2 and parts[1].isdigit():
                idx = int(parts[1]) - 1
                if 0 <= idx < len(SERVICES):
                    name, _, port, slug = SERVICES[idx]
                    url = f"http://localhost:{port}/aabhar/v1/{slug}/docs"
                    webbrowser.open(url)
                    print(f" 🌐 Opened docs for {name}: {url}")
                else:
                    print(" Invalid service number.")

        elif choice.startswith("r"):
            parts = choice.split()
            if len(parts) == 2 and parts[1].isdigit():
                idx = int(parts[1]) - 1
                if 0 <= idx < len(SERVICES):
                    name, app, port, slug = SERVICES[idx]
                    print(f" 🔄 Restarting {name} (port {port})...")
                    stop_service(name)
                    kill_port_owners([port])
                    clear_pycache()
                    start_service(name, app, port, slug)
                    timeout = HEALTH_TIMEOUT_OVERRIDES.get(name, DEFAULT_HEALTH_TIMEOUT)
                    _, ok = wait_for_service(name, port, timeout)
                    SERVICE_STATE[name]["healthy"] = ok
                else:
                    print(" Invalid service number.")
            else:
                print(" Usage: r <service_number> (e.g., r 3)")

        elif choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(SERVICES):
                name = SERVICES[idx][0]
                open_log_window(name)
            else:
                print(f" Please enter a number between 1 and {len(SERVICES)}.")

        else:
            matched = [name for name, _, _, _ in SERVICES if name.startswith(choice)]
            if len(matched) == 1:
                open_log_window(matched[0])
            else:
                print(" Unknown command. Type 's' to view the menu options.")


# ==========================================
# 8. MAIN EXECUTION FLOW
# ==========================================
def main() -> None:
    parser = argparse.ArgumentParser(description="FastAPI Local Microservices Orchestrator")
    parser.add_argument(
        "--docs",
        action="store_true",
        help="Automatically open all local OpenAPI documentation endpoints in your default browser.",
    )
    parser.add_argument(
        "--skip-infra",
        action="store_true",
        help="Continue starting services even if PostgreSQL or Redis fails the pre-flight check.",
    )
    args = parser.parse_args()

    try:
        # Step 1: Pre-flight cleanup of orphaned ports and stale bytecode
        print("\n🧹 Running pre-flight cleanup (killing orphaned port listeners & clearing __pycache__)...")
        kill_port_owners([port for _, _, port, _ in SERVICES])
        clear_pycache()

        # Step 2: Verify PostgreSQL and Redis stability before booting services
        infra_ok = verify_infrastructure(retries=3)
        if not infra_ok and not args.skip_infra:
            ans = input("\n⚠ PostgreSQL or Redis is unreachable/unstable. Continue anyway? [y/N]: ").strip().lower()
            if ans not in ("y", "yes"):
                print("Aborting startup. Please ensure PostgreSQL and Redis are running.")
                return

        # Step 3: Launch all services simultaneously in the background
        print("\n🚀 Launching all microservices...\n")
        for name, app, port, slug in SERVICES:
            print(f" • Spawning {name:<14} on port {port} -> .logs/{name}.log")
            start_service(name, app, port, slug)

        # Step 4: Wait for parallel health checks
        print("\n⏳ Waiting for all services to pass health checks...")
        with ThreadPoolExecutor(max_workers=len(SERVICES)) as executor:
            futures = {}
            for name, _, port, _ in SERVICES:
                timeout = HEALTH_TIMEOUT_OVERRIDES.get(name, DEFAULT_HEALTH_TIMEOUT)
                futures[executor.submit(wait_for_service, name, port, timeout)] = name

            for future in as_completed(futures):
                name, is_healthy = future.result()
                SERVICE_STATE[name]["healthy"] = is_healthy

        if args.docs:
            for _, _, port, slug in SERVICES:
                webbrowser.open(f"http://localhost:{port}/aabhar/v1/{slug}/docs")
            print("\n🌐 Opened documentation tabs in your default browser.")

        # Step 5: Enter interactive menu
        interactive_loop()

    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"\n❌ Orchestrator error: {e}")
    finally:
        shutdown_all_services()


if __name__ == "__main__":
    main()