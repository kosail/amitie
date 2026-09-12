"""POST /api/login — real credential verification (see SPECS.md §12 scope note).

Not part of the original SPECS.md §8 frozen A2UI contract; added alongside the
other plain-REST finance endpoints for the native login screen.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from auth.passwords import verify_password
from db.port import DatabasePort

from ..dependencies import get_database
from ..schemas import LoginRequest, LoginResponse
from .session import create_session_row

router = APIRouter(prefix="/api", tags=["auth"])

_INVALID_CREDENTIALS = HTTPException(status_code=401, detail="Usuario o contraseña incorrectos.")


@router.post("/login", response_model=LoginResponse)
async def login(
    payload: LoginRequest, database: DatabasePort = Depends(get_database)
) -> LoginResponse:
    row = await database.fetch_one(
        "SELECT u.id, u.username, u.password_hash, u.password_salt, a.mode AS accessibility_mode "
        "FROM users u LEFT JOIN accessibility_profiles a ON a.user_id = u.id "
        "WHERE u.username = ?",
        (payload.username.strip().lower(),),
    )
    if row is None or not row["password_hash"] or not row["password_salt"]:
        raise _INVALID_CREDENTIALS
    if not verify_password(payload.password, row["password_hash"], row["password_salt"]):
        raise _INVALID_CREDENTIALS

    session_id = await create_session_row(database, row["id"])
    return LoginResponse(
        session_id=session_id,
        user_id=row["id"],
        username=row["username"],
        accessibility_mode=row["accessibility_mode"],
    )
