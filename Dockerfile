
# =========================
# STAGE 1 — BUILDER
# =========================
FROM python:3.11-slim AS builder

# Pin uv to the version used locally
COPY --from=ghcr.io/astral-sh/uv:0.11.13 /uv /uvx /bin/

WORKDIR /app

# Build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Configure uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT="/app/venv" \
    PATH="/app/venv/bin:$PATH"

# Install locked production dependencies
COPY pyproject.toml uv.lock ./

RUN uv sync --frozen --no-dev --no-install-project

# Copy application source
COPY . .

# =========================
# STAGE 2 — RUNTIME
# =========================
FROM python:3.11-slim

WORKDIR /app

# Runtime libraries
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN addgroup --system appgroup && \
    adduser --system --group appuser

# Copy application and virtual environment
COPY --from=builder /app /app

# Configure permissions
RUN mkdir -p /app/logs && \
    chown -R appuser:appgroup /app && \
    chmod 755 /app/logs

ENV PATH="/app/venv/bin:$PATH" \
    PYTHONPATH="/app" \
    PYTHONUNBUFFERED=1

USER appuser

# Default: auth service.
# Kubernetes can override CMD arguments for other services.
ENTRYPOINT ["python", "-m", "uvicorn"]
CMD ["src.auth.main:app", "--host", "0.0.0.0", "--port", "8001"]
