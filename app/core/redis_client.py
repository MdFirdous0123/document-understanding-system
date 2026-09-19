"""Redis client for distributed state and caching."""
import redis
from app.core.config import settings

redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)


def get_redis():
    """Return the shared Redis client instance."""
    return redis_client
