"""POST /api/session."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends

from db.port import DatabasePort

from ..dependencies import get_database, now_iso
from ..schemas import SessionRequest, SessionResponse

router = APIRouter(prefix="/api", tags=["session"])


@router.post("/session", response_model=SessionResponse)
async def create_session(
    payload: SessionRequest, database: DatabasePort = Depends(get_database)
) -> SessionResponse:
    session_id = "sess_" + uuid.uuid4().hex[:12]
    now = now_iso()
    await database.execute(
        "INSERT INTO sessions (id, user_id, active_surface_id, context_json, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (session_id, payload.user_id, None, "{}", now, now),
    )
    return SessionResponse(session_id=session_id, user_id=payload.user_id)
