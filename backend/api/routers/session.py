"""POST /api/session."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends

from db.port import DatabasePort

from ..dependencies import get_database, now_iso
from ..schemas import SessionRequest, SessionResponse

router = APIRouter(prefix="/api", tags=["session"])


async def create_session_row(database: DatabasePort, user_id: str) -> str:
    """Insert a new `sessions` row and return its id. Shared with `POST /api/login`."""
    session_id = "sess_" + uuid.uuid4().hex[:12]
    now = now_iso()
    await database.execute(
        "INSERT INTO sessions (id, user_id, active_surface_id, context_json, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (session_id, user_id, None, "{}", now, now),
    )
    return session_id


@router.post("/session", response_model=SessionResponse)
@router.post("/sessions", response_model=SessionResponse, include_in_schema=False)
async def create_session(
    payload: SessionRequest, database: DatabasePort = Depends(get_database)
) -> SessionResponse:
    session_id = await create_session_row(database, payload.user_id)
    return SessionResponse(session_id=session_id, user_id=payload.user_id)
