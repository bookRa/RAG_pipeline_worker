"""Token bucket rate limiter for API calls."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)


class RateLimiter:
    """Token bucket rate limiter for controlling API request rates.
    
    Implements the token bucket algorithm to limit requests per minute.
    Supports async/await for non-blocking rate limiting in concurrent contexts.
    
    Example:
        >>> limiter = RateLimiter(requests_per_minute=60)
        >>> await limiter.acquire(tokens=1)  # Waits if rate limit would be exceeded
        >>> # Make API call here
    """

    def __init__(self, requests_per_minute: int, burst_size: Optional[int] = None) -> None:
        """Initialize the rate limiter.
        
        Args:
            requests_per_minute: Maximum number of requests allowed per minute
            burst_size: Maximum burst capacity (defaults to requests_per_minute)
        """
        self.requests_per_minute = requests_per_minute
        self.burst_size = burst_size or requests_per_minute
        self.tokens = float(self.burst_size)
        self.last_update = time.monotonic()
        self._lock = asyncio.Lock()
        
        # Calculate token refill rate (tokens per second)
        self.refill_rate = requests_per_minute / 60.0

    async def acquire(self, tokens: int = 1) -> None:
        """Acquire tokens, waiting if necessary to respect rate limit.
        
        This method will block (asynchronously) until enough tokens are available.
        
        Args:
            tokens: Number of tokens to acquire (default 1)
        """
        async with self._lock:
            while True:
                # Refill tokens based on elapsed time
                now = time.monotonic()
                elapsed = now - self.last_update
                self.tokens = min(self.burst_size, self.tokens + elapsed * self.refill_rate)
                self.last_update = now

                # Check if we have enough tokens
                if self.tokens >= tokens:
                    self.tokens -= tokens
                    return

                # Calculate wait time needed
                tokens_needed = tokens - self.tokens
                wait_time = tokens_needed / self.refill_rate

                logger.debug(
                    "Rate limit reached, waiting %.2fs for %d tokens",
                    wait_time,
                    tokens,
                )

                # Wait for tokens to refill (release lock while waiting)
                # Use a small buffer to avoid timing precision issues
                await asyncio.sleep(wait_time + 0.01)

    def try_acquire(self, tokens: int = 1) -> bool:
        """Try to acquire tokens without waiting.
        
        Args:
            tokens: Number of tokens to acquire (default 1)
            
        Returns:
            True if tokens were acquired, False if rate limit would be exceeded
        """
        # Refill tokens based on elapsed time
        now = time.monotonic()
        elapsed = now - self.last_update
        self.tokens = min(self.burst_size, self.tokens + elapsed * self.refill_rate)
        self.last_update = now

        # Check if we have enough tokens
        if self.tokens >= tokens:
            self.tokens -= tokens
            return True

        return False

    async def __aenter__(self) -> RateLimiter:
        """Context manager entry - acquire one token."""
        await self.acquire(1)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit - no-op."""
        pass

