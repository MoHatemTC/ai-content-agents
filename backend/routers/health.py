"""Infrastructure health probe (M0).

Not part of the frontend contract — a scaffold endpoint so deployments and the
test suite can confirm the app boots and the DI wiring works.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from backend.config import Settings
from backend.deps import settings_dependency

router = APIRouter(tags=["health"])


@router.get("/health")
def health(
    settings: Annotated[Settings, Depends(settings_dependency)],
) -> dict[str, str]:
    """Return a minimal liveness payload."""
    return {"status": "ok", "app": settings.app_name, "env": settings.app_env}
