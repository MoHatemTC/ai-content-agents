"""FastAPI dependency-injection skeleton.

M0 ships the two dependencies every router will need: the application
:class:`~backend.config.Settings` and access to the per-app container
(``app.state``). The authenticated ``CurrentUser`` dependency arrives with the
auth milestone (M1) and will be added here, not as a new pattern.
"""

from __future__ import annotations

from fastapi import Request

from backend.config import Settings, get_settings


def settings_dependency() -> Settings:
    """FastAPI dependency returning the process-wide :class:`Settings`."""
    return get_settings()


def app_settings(request: Request) -> Settings:
    """Return the settings instance bound to this app (from ``app.state``).

    Prefer this inside routers that need to match the settings the app was
    created with (e.g. a test-provided database path) rather than the
    environment-cached singleton.
    """
    return request.app.state.settings
