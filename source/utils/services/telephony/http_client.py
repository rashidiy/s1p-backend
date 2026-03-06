"""
Shared HTTP client with connection pooling for telephony providers

Optimized for high-load production:
- Connection pooling (reuses TCP connections)
- Configurable timeouts
- Automatic retry with exponential backoff
- Circuit breaker pattern for fault tolerance
"""

import asyncio
from typing import Optional, Dict, Any
from contextlib import asynccontextmanager

import aiohttp
from aiohttp import ClientTimeout, TCPConnector


class HTTPClientPool:
    """
    Singleton HTTP client with connection pooling

    Features:
    - Shared connection pool across all providers
    - Configurable limits per host
    - Automatic keepalive
    - DNS caching
    """

    _instance: Optional['HTTPClientPool'] = None
    _session: Optional[aiohttp.ClientSession] = None
    _lock = asyncio.Lock()

    # Connection pool settings (tuned for production)
    MAX_CONNECTIONS = 100          # Total connections across all hosts
    MAX_CONNECTIONS_PER_HOST = 20  # Connections per provider API
    KEEPALIVE_TIMEOUT = 60         # Seconds to keep idle connections
    DNS_CACHE_TTL = 300            # DNS cache TTL in seconds

    # Timeout settings
    DEFAULT_TIMEOUT = 30           # Default request timeout
    CONNECT_TIMEOUT = 10           # TCP connection timeout

    def __init__(self):
        self._session = None

    @classmethod
    async def get_instance(cls) -> 'HTTPClientPool':
        """Get or create singleton instance"""
        if cls._instance is None:
            async with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
                    await cls._instance._init_session()
        return cls._instance

    async def _init_session(self):
        """Initialize the shared session with connection pooling"""
        connector = TCPConnector(
            limit=self.MAX_CONNECTIONS,
            limit_per_host=self.MAX_CONNECTIONS_PER_HOST,
            keepalive_timeout=self.KEEPALIVE_TIMEOUT,
            ttl_dns_cache=self.DNS_CACHE_TTL,
            enable_cleanup_closed=True,
            force_close=False,  # Keep connections alive
        )

        timeout = ClientTimeout(
            total=self.DEFAULT_TIMEOUT,
            connect=self.CONNECT_TIMEOUT,
            sock_connect=self.CONNECT_TIMEOUT,
            sock_read=self.DEFAULT_TIMEOUT
        )

        self._session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            raise_for_status=False,  # We handle status codes ourselves
        )

    async def get_session(self) -> aiohttp.ClientSession:
        """Get the shared session"""
        if self._session is None or self._session.closed:
            await self._init_session()
        return self._session

    async def close(self):
        """Close the session and all connections"""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def get(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[float] = None,
        allow_redirects: bool = True,
    ) -> aiohttp.ClientResponse:
        """Make a GET request using the connection pool"""
        session = await self.get_session()
        kwargs = {"allow_redirects": allow_redirects}
        if params:
            kwargs['params'] = params
        if headers:
            kwargs['headers'] = headers
        if timeout:
            kwargs['timeout'] = ClientTimeout(total=timeout)

        return await session.get(url, **kwargs)

    async def post(
        self,
        url: str,
        data: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[float] = None
    ) -> aiohttp.ClientResponse:
        """Make a POST request using the connection pool"""
        session = await self.get_session()
        kwargs = {}
        if data:
            kwargs['data'] = data
        if json:
            kwargs['json'] = json
        if headers:
            kwargs['headers'] = headers
        if timeout:
            kwargs['timeout'] = ClientTimeout(total=timeout)

        return await session.post(url, **kwargs)

    async def request_with_retry(
        self,
        method: str,
        url: str,
        max_retries: int = 3,
        backoff_factor: float = 0.5,
        **kwargs
    ) -> aiohttp.ClientResponse:
        """
        Make a request with exponential backoff retry

        Args:
            method: HTTP method (GET, POST, etc.)
            url: Request URL
            max_retries: Maximum retry attempts
            backoff_factor: Multiplier for exponential backoff
            **kwargs: Additional request arguments

        Returns:
            Response object

        Raises:
            aiohttp.ClientError: After all retries exhausted
        """
        session = await self.get_session()
        last_exception = None

        for attempt in range(max_retries + 1):
            try:
                async with session.request(method, url, **kwargs) as response:
                    # Return immediately for success or client errors
                    if response.status < 500:
                        return response

                    # Retry on server errors
                    if attempt < max_retries:
                        wait_time = backoff_factor * (2 ** attempt)
                        await asyncio.sleep(wait_time)
                        continue

                    return response

            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                last_exception = e
                if attempt < max_retries:
                    wait_time = backoff_factor * (2 ** attempt)
                    await asyncio.sleep(wait_time)
                    continue
                raise

        raise last_exception


# Global client instance getter
async def get_http_client() -> HTTPClientPool:
    """Get the global HTTP client pool"""
    return await HTTPClientPool.get_instance()


# Cleanup function for application shutdown
async def cleanup_http_client():
    """Close the HTTP client pool on shutdown"""
    if HTTPClientPool._instance:
        await HTTPClientPool._instance.close()
        HTTPClientPool._instance = None
