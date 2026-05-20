"""Cache decorators."""
import json
import hashlib
from functools import wraps
from typing import Callable, Optional
from app.cache.manager import cache_manager


def cache_key(*args, **kwargs) -> str:
    """Generate cache key from function arguments."""
    key_parts = [str(arg) for arg in args]
    key_parts.extend([f"{k}={v}" for k, v in sorted(kwargs.items())])
    
    key_string = "|".join(key_parts)
    return hashlib.md5(key_string.encode()).hexdigest()


def cached(ttl: Optional[int] = None, key_prefix: str = ""):
    """Cache decorator for async functions."""
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Generate cache key
            func_key = f"{key_prefix}:{func.__name__}"
            cache_key_value = f"{func_key}:{cache_key(*args, **kwargs)}"
            
            # Try to get from cache
            cached_value = await cache_manager.get(cache_key_value)
            if cached_value is not None:
                return cached_value
            
            # Execute function
            result = await func(*args, **kwargs)
            
            # Store in cache
            await cache_manager.set(cache_key_value, result, ttl)
            
            return result
        
        return wrapper
    
    return decorator


def invalidate_cache(pattern: str):
    """Cache invalidation decorator."""
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            result = await func(*args, **kwargs)
            await cache_manager.clear_pattern(pattern)
            return result
        
        return wrapper
    
    return decorator
