"""
Shared per-IP rate limiter (slowapi) — single Limiter instance for the whole app.

SECURITY: Any endpoint that calls an external paid API (Claude, GitHub)
must be rate-limited. This is a standing requirement.

Import `limiter` and decorate the route with `@limiter.limit("N/hour")`.
slowapi requires the decorated function to accept a `request: Request` argument.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
