"""FastAPI router for admin dashboard endpoints.

Exposes GET /admin/stats — live site-wide totals computed from the platform
database, gated to staff (admin / reviewer) like the review endpoints.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from backend.admin.schemas import AdminStatsResponse
from backend.admin.service import get_admin_stats
from backend.auth.schemas import AuthUser
from backend.config import Settings
from backend.deps import get_settings, require_role

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/stats", response_model=AdminStatsResponse)
async def admin_stats(
    current_user: Annotated[AuthUser, Depends(require_role("admin", "reviewer"))],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AdminStatsResponse:
    """Live site-wide totals for the admin dashboard (staff only)."""
    return get_admin_stats(settings.platform_db_path)
