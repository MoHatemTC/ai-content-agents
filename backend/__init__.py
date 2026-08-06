"""FastAPI integration entrypoint package (Phase 8).

The ``backend/`` package is the HTTP layer for the Content Agents platform. It
wraps the existing domain implementation in ``src/`` (agents, ingestion,
retrieval, validation) without changing it; every module here is thin glue:
routers, request/response schemas, error envelopes, and infrastructure.

Milestone M0 (this package's foundation) ships only the scaffold: app factory,
settings, error envelope, CORS, migration runner, DI skeleton and a ``/health``
endpoint. No business routers exist yet — they land with their milestones.
"""

from __future__ import annotations

__version__ = "0.2.0"
