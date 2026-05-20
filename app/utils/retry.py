"""Retry utilities with exponential backoff."""
import asyncio
import functools
from typing import Callable, Type, Tuple
from app.core.logging import get_logger

logger = get_logger(__name__)


def retry(
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
):
    """Async retry decorator with exponential backoff."""
    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            attempt = 0
            current_delay = delay
            while attempt < max_attempts:
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    attempt += 1
                    if attempt >= max_attempts:
                        logger.error(
                            "retry_exhausted",
                            func=func.__name__,
                            attempts=attempt,
                            error=str(e),
                        )
                        raise
                    logger.warning(
                        "retry_attempt",
                        func=func.__name__,
                        attempt=attempt,
                        delay=current_delay,
                    )
                    await asyncio.sleep(current_delay)
                    current_delay *= backoff
        return wrapper
    return decorator


async def retry_async(
    coro,
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
):
    """Retry a coroutine with exponential backoff."""
    attempt = 0
    current_delay = delay
    while attempt < max_attempts:
        try:
            return await coro
        except Exception as e:
            attempt += 1
            if attempt >= max_attempts:
                raise
            await asyncio.sleep(current_delay)
            current_delay *= backoff
