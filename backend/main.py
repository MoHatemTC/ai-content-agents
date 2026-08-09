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
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Load the repository .env from an absolute path so the app works no matter
# which working directory uvicorn is launched from. Without this the gateway
# credentials are missing and generation would fall back to fabricated output.
try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
except Exception:  # pragma: no cover - python-dotenv is a dev convenience
    pass

from backend import __version__
from backend.admin.router import router as admin_router
from backend.auth.router import router as auth_router
from backend.auth.seed import seed_if_empty
from backend.chat.router import router as chat_router
from backend.config import Settings, get_settings
from backend.db import connect
from backend.documents.router import (
    router as documents_router,
)
from backend.documents.router import (
    upload_router as documents_upload_router,
)
from backend.errors import register_exception_handlers
from backend.exports.router import router as exports_router
from backend.generation.router import router as generation_router
from backend.history.router import router as history_router
from backend.migrations import run_pending
from backend.review.router import router as review_router
from backend.routers import health
from backend.search.router import router as search_router
from backend.workspaces.router import router as workspaces_router


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build a fully-wired FastAPI application.

    Args:
        settings: Optional explicit settings; defaults to the environment.
    """
    resolved = settings or get_settings()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        run_pending(resolved.platform_db_path)
        conn = connect(resolved.platform_db_path)
        try:
            seed_if_empty(conn)
        finally:
            conn.close()
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
    app.include_router(auth_router)
    app.include_router(workspaces_router)
    app.include_router(documents_upload_router)
    app.include_router(documents_router)
    app.include_router(search_router)
    app.include_router(generation_router)
    app.include_router(history_router)
    app.include_router(chat_router)
    app.include_router(review_router)
    app.include_router(exports_router)
    app.include_router(admin_router)
    return app


app = create_app()
