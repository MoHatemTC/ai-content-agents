"""FastAPI application factory (M0 scaffold).

Composes the backend's infrastructure into a runnable app:

* settings bound to ``app.state``,
* CORS middleware (origins from ``Settings.cors_origins``),
* contract-shaped error envelope handlers (:mod:`backend.errors`),
* pending schema migrations applied on startup (:mod:`backend.migrations`),
* routers (only :mod:`backend.routers.health` at M0).

``create_app`` accepts an explicit :class:`~backend.config.Settings` so tests
can point the app at a temporary database without touching the environment.

Run the server with::

    uvicorn backend.main:app --reload
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend import __version__
from backend.config import Settings, get_settings
from backend.errors import register_exception_handlers
from backend.migrations import run_pending
from backend.routers import health


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build a fully-wired FastAPI application.

    Args:
        settings: Optional explicit settings; defaults to the environment.
    """
    resolved = settings or get_settings()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        run_pending(resolved.platform_db_path)
        yield

    app = FastAPI(
        title=resolved.app_name,
        version=__version__,
        lifespan=lifespan,
    )
    app.state.settings = resolved

    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved.cors_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)
    app.include_router(health.router)
    return app


app = create_app()
