"""M4 search API route (GET /search).

Satisfies the consumer-defined search facade (Sensei-AI/src/api/paths.ts
``search: "/search"``, src/api/search.api.ts ``GET /search?q=&workspace_id=
&limit=&kinds=``) with document-kind results from the workspace's Chroma
index. Scope and errors mirror the documents routes: a workspace is only
searchable by its owner (403 otherwise, 404 when it does not exist), and
missing/invalid parameters surface the contract's 422 envelope.
"""

from __future__ import annotations

import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from backend.auth.schemas import AuthUser
from backend.deps import get_current_user, get_db
from backend.errors import ApiError
from backend.workspaces import service as workspaces_service

from .schemas import SearchResponse
from .service import DEFAULT_SEARCH_LIMIT, search_workspace

router = APIRouter(prefix="/search", tags=["search"])

Db = Annotated[sqlite3.Connection, Depends(get_db)]
User = Annotated[AuthUser, Depends(get_current_user)]


def _require_owned_workspace(
    db: sqlite3.Connection, user: AuthUser, workspace_id: str
) -> None:
    row = workspaces_service.get_workspace(db, workspace_id)
    if row is None:
        raise ApiError(status_code=404, code="not_found", message="Workspace not found")
    if row["owner_id"] != user.id:
        raise ApiError(
            status_code=403,
            code="forbidden",
            message="Not allowed to access this workspace",
        )


@router.get("", response_model=SearchResponse)
def search(
    db: Db,
    user: User,
    request: Request,
    q: Annotated[str, Query()],
    workspace_id: Annotated[str, Query()],
    limit: Annotated[int, Query(ge=1, le=100)] = DEFAULT_SEARCH_LIMIT,
    kinds: Annotated[list[str] | None, Query()] = None,
) -> SearchResponse:
    """Return document results ranked against the workspace's indexed content."""
    _require_owned_workspace(db, user, workspace_id)
    return search_workspace(
        db,
        workspace_id,
        q,
        limit=limit,
        kinds=kinds,
        chroma_dir=request.app.state.settings.chroma_dir,
    )
