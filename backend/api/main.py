"""FastAPI application for Paradigm — agentic research platform."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routes import agents, config, papers, research, sessions, settings, ws
from backend.api.services.session_manager import SessionManager

logger = logging.getLogger(__name__)


def _load_paradigm_config() -> Any:
    """Load Paradigm config.

    Tries the full ``paradigm.config.load_config`` first (available when running
    on Python 3.11+).  Falls back to the lightweight backend-local loader so
    that routes still work on Python 3.10 where the core package cannot be
    imported.
    """
    try:
        from paradigm.config import load_config

        return load_config()
    except Exception:
        pass

    # Fallback: lightweight backend-local loader
    try:
        from backend.api.config import load_backend_config

        cfg = load_backend_config()
        logger.info("Loaded backend-local config (paradigm core not available)")
        return cfg
    except Exception as e:
        logger.warning("Could not load any config: %s", e)
        return None


def _init_database(config: Any) -> Any:
    """Initialize the shared Database instance."""
    if config is None:
        return None
    try:
        from paradigm.storage.database import Database

        db = Database(config.storage.db_path)
        # Enable WAL mode for concurrent reads during writes
        db.conn.execute("PRAGMA journal_mode=WAL")
        return db
    except Exception as e:
        logger.warning("Could not initialize database: %s", e)
        return None


def _init_event_logger(config: Any) -> Any:
    """Initialize the shared EventLogger."""
    if config is None:
        return None
    try:
        from paradigm.logging.events import EventLogger

        return EventLogger(config.storage.log_path)
    except Exception as e:
        logger.warning("Could not initialize event logger: %s", e)
        return None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: initialize and teardown shared resources."""
    # Startup
    config = _load_paradigm_config()
    database = _init_database(config)
    event_logger = _init_event_logger(config)

    session_manager = SessionManager(
        config=config,
        database=database,
        event_logger=event_logger,
    )

    # Store in app state for dependency injection
    app.state.config = config
    app.state.database = database
    app.state.event_logger = event_logger
    app.state.session_manager = session_manager

    logger.info("Paradigm API started")
    yield

    # Shutdown: cancel all running sessions
    await session_manager.shutdown()

    if database is not None:
        database.close()

    logger.info("Paradigm API stopped")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Paradigm API",
        description="Web API for the Paradigm agentic research platform",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS — configurable via PARADIGM_CORS_ORIGINS env var.
    # Defaults to localhost dev origins. Set to comma-separated list for production.
    cors_origins_str = os.getenv(
        "PARADIGM_CORS_ORIGINS", "http://localhost:3000,http://localhost:5173"
    )
    cors_origins = [o.strip() for o in cors_origins_str.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Content-Type", "X-API-Key"],
    )

    # Health check
    @app.get("/health", tags=["utility"])
    async def health_check() -> dict[str, str]:
        return {"status": "ok", "service": "paradigm-api"}

    # Register routers
    app.include_router(research.router)
    app.include_router(sessions.router)
    app.include_router(agents.router)
    app.include_router(papers.router)
    app.include_router(config.router)
    app.include_router(settings.router)
    app.include_router(ws.router)

    return app


app = create_app()
