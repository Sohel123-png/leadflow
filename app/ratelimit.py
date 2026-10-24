import time

import redis
from fastapi import HTTPException, Request

from app.cache import get_redis
from app.config import settings


def rate_limit(request: Request) -> None:
    """Fixed-window limiter: max N requests per minute per client IP (Redis INCR + EXPIRE)."""
    client = get_redis()
    if client is None:
        return
    ip = request.client.host if request.client else "unknown"
    key = f"rl:{ip}:{int(time.time() // 60)}"
    try:
        count = client.incr(key)
        if count == 1:
            client.expire(key, 60)
    except redis.RedisError:
        return  # fail open: never block users because Redis is down
    if count > settings.rate_limit_per_minute:
        raise HTTPException(
            status_code=429,
            detail="Too many requests, slow down",
            headers={"Retry-After": "60"},
        )
