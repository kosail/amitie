"""Voice-first loans & credits consult endpoints (see LOANS_CONSULT_GUIDE.md)."""

from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Depends, HTTPException

from agent.loans import LoansConsultService
from db.port import DatabasePort
from mcp_servers.toolbox import Toolbox

from ..dependencies import get_database, get_loans_service, get_toolbox, now_iso
from ..schemas import (
    LoansConsultRequest,
    LoansConsultResponse,
    LoansGreetingRequest,
    LoansGreetingResponse,
)

router = APIRouter(prefix="/api/loans", tags=["loans"])


async def _create_loan_request(database: DatabasePort, user_id: str) -> str:
    loan_id = "loan_" + uuid.uuid4().hex[:10]
    now = now_iso()
    await database.execute(
        "INSERT INTO loan_requests (id, user_id, status, context_json, created_at, updated_at) "
        "VALUES (?,?,?,?,?,?)",
        (loan_id, user_id, "open", "{}", now, now),
    )
    return loan_id


async def _history(database: DatabasePort, loan_id: str) -> list[dict[str, str]]:
    row = await database.fetch_one(
        "SELECT context_json FROM loan_requests WHERE id = ?", (loan_id,)
    )
    if row is None:
        return []
    return list(json.loads(row["context_json"] or "{}").get("turns", []))


async def _append_turns(
    database: DatabasePort, loan_id: str, turns: list[dict[str, str]]
) -> None:
    row = await database.fetch_one(
        "SELECT context_json FROM loan_requests WHERE id = ?", (loan_id,)
    )
    context = json.loads(row["context_json"] or "{}") if row else {}
    context.setdefault("turns", []).extend(turns)
    await database.execute(
        "UPDATE loan_requests SET context_json = ?, updated_at = ? WHERE id = ?",
        (json.dumps(context, ensure_ascii=False), now_iso(), loan_id),
    )


@router.post("/greeting", response_model=LoansGreetingResponse)
async def greeting(
    payload: LoansGreetingRequest,
    database: DatabasePort = Depends(get_database),
    loans: LoansConsultService = Depends(get_loans_service),
) -> LoansGreetingResponse:
    session_id = "sess_" + uuid.uuid4().hex[:12]
    now = now_iso()
    await database.execute(
        "INSERT INTO sessions (id, user_id, active_surface_id, context_json, created_at, updated_at) "
        "VALUES (?,?,?,?,?,?)",
        (session_id, payload.user_id, None, "{}", now, now),
    )
    result = await loans.greeting(user_id=payload.user_id)
    return LoansGreetingResponse(session_id=session_id, **result)


@router.post("/consult", response_model=LoansConsultResponse)
async def consult(
    payload: LoansConsultRequest,
    database: DatabasePort = Depends(get_database),
    toolbox: Toolbox = Depends(get_toolbox),
    loans: LoansConsultService = Depends(get_loans_service),
) -> LoansConsultResponse:
    session = await database.fetch_one(
        "SELECT id, user_id FROM sessions WHERE id = ?", (payload.session_id,)
    )
    if session is None:
        raise HTTPException(status_code=404, detail="unknown session")
    user_id = session["user_id"]

    text = payload.text
    if payload.audio_b64 and not text:
        transcription = await toolbox.call(
            "transcribe_audio",
            {"audio_b64": payload.audio_b64, "language": payload.language},
        )
        if transcription.get("status") != "ok":
            issues = transcription.get("issues") or ["could not transcribe audio"]
            return LoansConsultResponse(
                status="error",
                error_code="transcription_failed",
                retryable=True,
                message="; ".join(issues),
            )
        text = transcription.get("text")
    if not text:
        return LoansConsultResponse(
            status="error", error_code="bad_request", message="text or audio is required"
        )

    loan_id = payload.loan_request_id
    if loan_id:
        existing = await database.fetch_one(
            "SELECT id FROM loan_requests WHERE id = ?", (loan_id,)
        )
        if existing is None:
            raise HTTPException(status_code=404, detail="unknown loan request")
    else:
        loan_id = await _create_loan_request(database, user_id)

    history = await _history(database, loan_id)
    result = await loans.consult(
        user_id=user_id, text=text, loan_request_id=loan_id, history=history
    )
    if result.get("status") == "ok":
        await _append_turns(
            database,
            loan_id,
            [
                {"role": "user", "text": text},
                {"role": "assistant", "text": result.get("response_text", "")},
            ],
        )
        if result.get("terminal_response"):
            await database.execute(
                "UPDATE loan_requests SET status = 'terminal', updated_at = ? WHERE id = ?",
                (now_iso(), loan_id),
            )
    return LoansConsultResponse(**result)


@router.get("/{loan_request_id}", response_model=LoansConsultResponse)
async def get_loan(
    loan_request_id: str,
    database: DatabasePort = Depends(get_database),
    toolbox: Toolbox = Depends(get_toolbox),
) -> LoansConsultResponse:
    row = await database.fetch_one(
        "SELECT id FROM loan_requests WHERE id = ?", (loan_request_id,)
    )
    if row is None:
        raise HTTPException(status_code=404, detail="unknown loan request")

    surface = await database.fetch_one(
        "SELECT id FROM generated_ui WHERE domain = 'loans_credits' AND entity_id = ? "
        "ORDER BY updated_at DESC, rowid DESC LIMIT 1",
        (loan_request_id,),
    )
    terminal = None
    audio_ref = None
    if surface is not None:
        hydrated = await toolbox.call("hydrate_ui", {"surface_id": surface["id"]})
        if hydrated.get("status") == "ok":
            audio_ref = hydrated.get("audio_ref")
            terminal = {
                "catalog_id": hydrated.get("catalog_id"),
                "surface_id": surface["id"],
                "a2ui": hydrated.get("a2ui", []),
            }
    return LoansConsultResponse(
        status="ok",
        loan_request_id=loan_request_id,
        terminal_response=terminal,
        audio_ref=audio_ref,
    )
