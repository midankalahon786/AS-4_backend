import logging
import os
import redis.asyncio as aioredis
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

redis: aioredis.Redis | None = None


def get_redis_url() -> str:
    return os.environ.get("REDIS_URL", "redis://localhost:6379/0")


def is_redis_disabled() -> bool:
    if os.getenv("REDIS_DISABLED", "").strip().lower() in ("true", "1", "yes"):
        return True
    if os.getenv("REDIS_ENABLED", "").strip().lower() in ("false", "0", "no"):
        return True
    return False


def is_redis_connected() -> bool:
    return redis is not None


async def connect_redis() -> aioredis.Redis:
    global redis

    if is_redis_disabled():
        redis = None
        logger.info("Redis is disabled via environment variable")
        raise RuntimeError("Redis is disabled via environment variable")

    url = get_redis_url()
    try:
        r = aioredis.from_url(
            url,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=10,
            socket_timeout=None,  # Crucial: Disables client-side read timeout on blocking stream reads
            health_check_interval=15,  # Pings Redis periodically to prevent idle TCP drops
            retry_on_timeout=True,
            retry_on_error=[ConnectionError, TimeoutError],
            max_connections=50,
        )

        await r.ping()
        redis = r

        host = url.split("@")[-1] if "@" in url else url
        logger.info("Redis connected → %s", host)
        return redis
    except Exception as exc:
        host = url.split("@")[-1] if "@" in url else url
        logger.warning("Redis connection failed (%s): %s", host, exc)
        redis = None
        raise


async def disconnect_redis():
    global redis
    if redis:
        try:
            await redis.aclose()
        except Exception:
            pass
        finally:
            redis = None
            logger.info("Redis disconnected")


def get_redis() -> aioredis.Redis:
    if redis is None:
        raise RuntimeError(
            "Redis not initialised — call connect_redis() in lifespan first."
        )
    return redis
