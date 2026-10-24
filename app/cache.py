"""Small Redis cache layer.

Every function degrades gracefully: if Redis is disabled or unreachable the app
keeps working, it just skips caching. Cache invalidation uses a version counter:
cache keys include the current version and any write to leads bumps it, so all
older entries become unreachable and expire on their own through the TTL.
"""
import hashlib
import json
from typing import Any

import redis

from app.config import settings

_client: redis.Redis | None = None
VERSION_KEY = "leads:version"


def get_redis() -> redis.Redis | None:
    global _client
    if not settings.redis_enabled:
        return None
    if _client is None:
        _client = redis.Redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=0.5,
            socket_timeout=0.5,
        )
    return _client


def get_version() -> int:
    client = get_redis()
    if client is None:
        return 0
    try:
        return int(client.get(VERSION_KEY) or 0)
    except redis.RedisError:
        return 0


def bump_version() -> None:
    client = get_redis()
    if client is None:
        return
    try:
        client.incr(VERSION_KEY)
    except redis.RedisError:
        pass


def make_key(prefix: str, *parts: Any) -> str:
    raw = "|".join(str(p) for p in parts)
    digest = hashlib.sha1(raw.encode()).hexdigest()
    return f"{prefix}:v{get_version()}:{digest}"


def cache_get(key: str) -> Any | None:
    client = get_redis()
    if client is None:
        return None
    try:
        value = client.get(key)
    except redis.RedisError:
        return None
    return json.loads(value) if value else None


def cache_set(key: str, value: Any) -> None:
    client = get_redis()
    if client is None:
        return
    try:
        client.set(key, json.dumps(value), ex=settings.cache_ttl_seconds)
    except redis.RedisError:
        pass
