"""Authentication middleware placeholder.

Provides a simple API key check via the X-API-Key header.
In production, replace with JWT or OAuth2.
"""

from __future__ import annotations

import logging
import os
import secrets

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

logger = logging.getLogger(__name__)

_API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


def _get_expected_key() -> str | None:
    """Return the expected API key from the environment (cached per-call)."""
    return os.getenv("PARADIGM_API_KEY")


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
    expected = _get_expected_key()
    if expected is None:
        # Auth disabled — dev mode
        return None
    if api_key is None or not secrets.compare_digest(api_key, expected):
        logger.warning("Rejected API key attempt")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )
    return api_key


def verify_api_key_sync(api_key: str | None) -> bool:
    """Synchronous API key check for WebSocket auth.

    Returns True if the key is valid or auth is disabled.
    """
    expected = _get_expected_key()
    if expected is None:
        return True  # Auth disabled — dev mode
    if api_key is None:
        return False
    return secrets.compare_digest(api_key, expected)
