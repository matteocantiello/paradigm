"""Authentication middleware placeholder.

Provides a simple API key check via the X-API-Key header.
In production, replace with JWT or OAuth2.
"""

from __future__ import annotations

import os

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

_API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(
    api_key: str | None = Security(_API_KEY_HEADER),
) -> str | None:
    """Verify the API key if PARADIGM_API_KEY is set.

    If PARADIGM_API_KEY is not set, authentication is disabled (dev mode).

    Returns:
        The validated API key, or None if auth is disabled.

    Raises:
        HTTPException: If the key is missing or invalid.
    """
    expected = os.getenv("PARADIGM_API_KEY")
    if expected is None:
        # Auth disabled — dev mode
        return None
    if api_key is None or api_key != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )
    return api_key
