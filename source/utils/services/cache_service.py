"""
Cache Service - High-performance caching for analytics and frequently accessed data

Supports:
- In-memory caching (for development/single instance)
- Redis caching (for production/multi-instance)
- Automatic cache invalidation
- TTL-based expiration
"""

import asyncio
import hashlib
import json
from datetime import datetime, timedelta
from functools import wraps
from typing import Any, Callable, Optional, TypeVar, Union
from uuid import UUID

# Try to import redis, fall back to in-memory cache if not available
try:
    import redis.asyncio as redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False


class InMemoryCache:
    """
    Simple in-memory cache for development/testing

    Thread-safe using asyncio locks.
    Automatically cleans expired entries.
    """

    def __init__(self):
        self._cache: dict = {}
        self._expiry: dict = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache"""
        async with self._lock:
            if key not in self._cache:
                return None

            # Check expiry
            if key in self._expiry and datetime.now() > self._expiry[key]:
                del self._cache[key]
                del self._expiry[key]
                return None

            return self._cache[key]

    async def set(self, key: str, value: Any, ttl: int = 300) -> None:
        """Set value in cache with TTL (seconds)"""
        async with self._lock:
            self._cache[key] = value
            self._expiry[key] = datetime.now() + timedelta(seconds=ttl)

    async def delete(self, key: str) -> None:
        """Delete key from cache"""
        async with self._lock:
            self._cache.pop(key, None)
            self._expiry.pop(key, None)

    async def delete_pattern(self, pattern: str) -> int:
        """Delete all keys matching pattern (glob-style)"""
        import fnmatch
        async with self._lock:
            keys_to_delete = [
                k for k in self._cache.keys()
                if fnmatch.fnmatch(k, pattern)
            ]
            for key in keys_to_delete:
                self._cache.pop(key, None)
                self._expiry.pop(key, None)
            return len(keys_to_delete)

    async def clear(self) -> None:
        """Clear all cache entries"""
        async with self._lock:
            self._cache.clear()
            self._expiry.clear()

    async def cleanup_expired(self) -> int:
        """Remove expired entries (for periodic cleanup)"""
        async with self._lock:
            now = datetime.now()
            expired_keys = [
                k for k, exp in self._expiry.items()
                if now > exp
            ]
            for key in expired_keys:
                self._cache.pop(key, None)
                self._expiry.pop(key, None)
            return len(expired_keys)


class RedisCache:
    """
    Redis-based cache for production

    Supports connection pooling and cluster mode.
    """

    def __init__(self, url: str = "redis://localhost:6379", prefix: str = "sip:"):
        self.url = url
        self.prefix = prefix
        self._client: Optional[Any] = None

    async def _get_client(self) -> Any:
        """Get or create Redis client"""
        if self._client is None:
            self._client = redis.from_url(
                self.url,
                encoding="utf-8",
                decode_responses=True
            )
        return self._client

    def _make_key(self, key: str) -> str:
        """Add prefix to key"""
        return f"{self.prefix}{key}"

    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache"""
        client = await self._get_client()
        value = await client.get(self._make_key(key))
        if value is None:
            return None
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value

    async def set(self, key: str, value: Any, ttl: int = 300) -> None:
        """Set value in cache with TTL (seconds)"""
        client = await self._get_client()
        serialized = json.dumps(value, default=str)
        await client.setex(self._make_key(key), ttl, serialized)

    async def delete(self, key: str) -> None:
        """Delete key from cache"""
        client = await self._get_client()
        await client.delete(self._make_key(key))

    async def delete_pattern(self, pattern: str) -> int:
        """Delete all keys matching pattern"""
        client = await self._get_client()
        keys = []
        async for key in client.scan_iter(match=self._make_key(pattern)):
            keys.append(key)
        if keys:
            await client.delete(*keys)
        return len(keys)

    async def clear(self) -> None:
        """Clear all cache entries with our prefix"""
        await self.delete_pattern("*")

    async def close(self) -> None:
        """Close Redis connection"""
        if self._client:
            await self._client.close()
            self._client = None


class CacheService:
    """
    Unified cache service

    Automatically uses Redis if available, falls back to in-memory cache.
    """

    _instance: Optional['CacheService'] = None
    _cache: Union[InMemoryCache, 'RedisCache']

    # Default TTLs for different data types
    TTL_SHORT = 60           # 1 minute - real-time data
    TTL_MEDIUM = 300         # 5 minutes - analytics
    TTL_LONG = 900           # 15 minutes - dashboard summaries
    TTL_VERY_LONG = 3600     # 1 hour - historical data

    def __init__(self, redis_url: Optional[str] = None):
        if redis_url and REDIS_AVAILABLE:
            self._cache = RedisCache(redis_url)
            self._using_redis = True
        else:
            self._cache = InMemoryCache()
            self._using_redis = False

    @classmethod
    def get_instance(cls, redis_url: Optional[str] = None) -> 'CacheService':
        """Get singleton instance"""
        if cls._instance is None:
            cls._instance = cls(redis_url)
        return cls._instance

    @staticmethod
    def _serialize_key(*args, **kwargs) -> str:
        """Create cache key from arguments"""
        key_parts = []

        for arg in args:
            if isinstance(arg, UUID):
                key_parts.append(str(arg))
            elif isinstance(arg, (datetime, )):
                key_parts.append(arg.isoformat())
            elif hasattr(arg, 'isoformat'):
                key_parts.append(arg.isoformat())
            else:
                key_parts.append(str(arg))

        for k, v in sorted(kwargs.items()):
            if isinstance(v, UUID):
                key_parts.append(f"{k}:{v}")
            elif v is not None:
                key_parts.append(f"{k}:{v}")

        return ":".join(key_parts)

    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache"""
        return await self._cache.get(key)

    async def set(self, key: str, value: Any, ttl: int = TTL_MEDIUM) -> None:
        """Set value in cache"""
        await self._cache.set(key, value, ttl)

    async def delete(self, key: str) -> None:
        """Delete key from cache"""
        await self._cache.delete(key)

    async def invalidate_company(self, company_id: UUID) -> int:
        """Invalidate all cache entries for a company"""
        pattern = f"*{company_id}*"
        return await self._cache.delete_pattern(pattern)

    async def invalidate_user(self, user_id: UUID) -> int:
        """Invalidate all cache entries for a user"""
        pattern = f"*{user_id}*"
        return await self._cache.delete_pattern(pattern)

    async def invalidate_analytics(self) -> int:
        """Invalidate all analytics cache"""
        return await self._cache.delete_pattern("analytics:*")

    # Convenience methods for common cache operations

    async def get_platform_analytics(
        self,
        owner_id: UUID,
        period: str
    ) -> Optional[dict]:
        """Get cached platform analytics"""
        key = f"analytics:platform:{owner_id}:{period}"
        return await self.get(key)

    async def set_platform_analytics(
        self,
        owner_id: UUID,
        period: str,
        data: dict,
        ttl: int = TTL_MEDIUM
    ) -> None:
        """Cache platform analytics"""
        key = f"analytics:platform:{owner_id}:{period}"
        await self.set(key, data, ttl)

    async def get_team_analytics(
        self,
        company_id: UUID,
        period: str
    ) -> Optional[dict]:
        """Get cached team analytics"""
        key = f"analytics:team:{company_id}:{period}"
        return await self.get(key)

    async def set_team_analytics(
        self,
        company_id: UUID,
        period: str,
        data: dict,
        ttl: int = TTL_MEDIUM
    ) -> None:
        """Cache team analytics"""
        key = f"analytics:team:{company_id}:{period}"
        await self.set(key, data, ttl)

    async def get_operator_analytics(
        self,
        user_id: UUID,
        period: str
    ) -> Optional[dict]:
        """Get cached operator analytics"""
        key = f"analytics:operator:{user_id}:{period}"
        return await self.get(key)

    async def set_operator_analytics(
        self,
        user_id: UUID,
        period: str,
        data: dict,
        ttl: int = TTL_SHORT
    ) -> None:
        """Cache operator analytics"""
        key = f"analytics:operator:{user_id}:{period}"
        await self.set(key, data, ttl)

    async def get_dashboard(
        self,
        entity_type: str,  # 'owner', 'admin', 'operator'
        entity_id: UUID
    ) -> Optional[dict]:
        """Get cached dashboard data"""
        key = f"dashboard:{entity_type}:{entity_id}"
        return await self.get(key)

    async def set_dashboard(
        self,
        entity_type: str,
        entity_id: UUID,
        data: dict,
        ttl: int = TTL_MEDIUM
    ) -> None:
        """Cache dashboard data"""
        key = f"dashboard:{entity_type}:{entity_id}"
        await self.set(key, data, ttl)


# Decorator for caching function results
T = TypeVar('T')


def cached(
    key_prefix: str,
    ttl: int = CacheService.TTL_MEDIUM,
    key_builder: Optional[Callable[..., str]] = None
):
    """
    Decorator to cache async function results

    Usage:
        @cached("analytics:calls", ttl=300)
        async def get_call_stats(company_id: UUID, period: str):
            ...

    Args:
        key_prefix: Prefix for cache key
        ttl: Time-to-live in seconds
        key_builder: Optional function to build cache key from args
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            cache = CacheService.get_instance()

            # Build cache key
            if key_builder:
                key = f"{key_prefix}:{key_builder(*args, **kwargs)}"
            else:
                key = f"{key_prefix}:{cache._serialize_key(*args, **kwargs)}"

            # Try to get from cache
            cached_value = await cache.get(key)
            if cached_value is not None:
                return cached_value

            # Call function and cache result
            result = await func(*args, **kwargs)

            # Only cache if result is not None
            if result is not None:
                # Handle Pydantic models
                if hasattr(result, 'model_dump'):
                    await cache.set(key, result.model_dump(), ttl)
                elif hasattr(result, 'dict'):
                    await cache.set(key, result.dict(), ttl)
                else:
                    await cache.set(key, result, ttl)

            return result

        return wrapper
    return decorator


# Global cache instance
_cache: Optional[CacheService] = None


def get_cache() -> CacheService:
    """Get global cache instance"""
    global _cache
    if _cache is None:
        import os
        redis_url = os.getenv('REDIS_URL')
        _cache = CacheService(redis_url)
    return _cache
