"""Voice-first loans & credits consult endpoints (see LOANS_CONSULT_GUIDE.md)."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from agent.loans import LoansConsultService
from db.port import DatabasePort
from mcp_servers.toolbox import Toolbox

from ..dependencies import (
    get_database,
    get_loan_detail_service,
    get_loans_service,
    get_toolbox,
    now_iso,
)
from ..schemas import (
    LoanDetailResponse,
    LoanResponse,
    LoansConsultRequest,
    LoansConsultResponse,
    LoansCreateRequest,
    LoansGreetingRequest,
    LoansListResponse,
)

router = APIRouter(prefix="/api/loans", tags=["loans"])

_CREDITOR_KIND_LABEL = {
    "credit_card": "Tarjeta de crédito",
    "payroll_loan": "Préstamo de nómina",
    "personal_loan": "Préstamo personal",
    "store_credit": "Crédito departamental",
}


async def _list_items(database: DatabasePort, toolbox: Toolbox, user_id: str) -> list[dict]:
    """One list for the Préstamos tab: created loans first, then active liabilities."""
    loans_result = await toolbox.call("list_loans", {"user_id": user_id})
    liabilities_result = await toolbox.call("get_liabilities", {"user_id": user_id})
    items: list[dict] = []
    for loan in loans_result.get("loans", []):
        items.append(
            {
                "source": "loan",
                "id": loan["id"],
                "name": "Crédito personal",
                "status": loan.get("status", "active"),
                "balance": loan.get("amount"),
                "monthlyPayment": loan.get("monthlyPayment"),
                "progressPercent": 0,
                "termMonths": loan.get("termMonths"),
                "purpose": loan.get("purpose"),
                "purposePrivate": bool(loan.get("purposePrivate")),
                "dueDay": None,
                "createdAt": loan.get("createdAt"),
            }
        )
    for liability in liabilities_result.get("liabilities", []):
        if liability.get("status") != "active":
            continue
        principal = float(liability.get("principal") or 0.0)
        balance = float(liability.get("balance") or 0.0)
        progress = round((principal - balance) / principal * 100) if principal > 0 else 0
        items.append(
            {
                "source": "liability",
                "id": liability["id"],
                "name": f"{liability.get('creditor')} · "
                f"{_CREDITOR_KIND_LABEL.get(liability.get('kind'), liability.get('kind'))}",
                "status": "active",
                "balance": liability.get("balance"),
                "monthlyPayment": liability.get("minPayment"),
                "progressPercent": max(0, min(100, progress)),
                "termMonths": None,
                "purpose": None,
                "purposePrivate": False,
                "dueDay": liability.get("dueDay"),
                "createdAt": None,
            }
        )
    return items


async def _audio_bytes(toolbox: Toolbox, audio_id: str | None) -> bytes | None:
    if not audio_id:
        return None
    meta = await toolbox.call("get_audio", {"asset_id": audio_id})
    file_path = meta.get("file_path") if isinstance(meta, dict) else None
    if file_path and Path(file_path).is_file():
        return Path(file_path).read_bytes()
    return None


def _multipart(payload: dict, audio: bytes | None, filename: str = "reply.mp3") -> Response:
    """Return `multipart/form-data` with a JSON `payload` part and an `audio` mp3 part."""
    boundary = "----lamamesa" + uuid.uuid4().hex
    chunks: list[bytes] = []

    def add(name: str, data: bytes, ctype: str | None = None, fname: str | None = None) -> None:
        disposition = f'Content-Disposition: form-data; name="{name}"'
        if fname:
            disposition += f'; filename="{fname}"'
        head = f"--{boundary}\r\n{disposition}\r\n"
        if ctype:
            head += f"Content-Type: {ctype}\r\n"
        head += "\r\n"
        chunks.append(head.encode("utf-8") + data + b"\r\n")

    add("payload", json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json")
    if audio:
        add("audio", audio, "audio/mpeg", filename)
    chunks.append(f"--{boundary}--\r\n".encode("utf-8"))
    return Response(
        content=b"".join(chunks), media_type=f"multipart/form-data; boundary={boundary}"
    )


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


_STATE_KEYS = (
    "requested_amount",
    "purpose",
    "purpose_private",
    "use_max",
    "requested_term",
    "term_confirmed",
    "purpose_asked",
)


async def _load_state(database: DatabasePort, loan_id: str) -> dict:
    row = await database.fetch_one(
        "SELECT context_json FROM loan_requests WHERE id = ?", (loan_id,)
    )
    if row is None:
        return {}
    context = json.loads(row["context_json"] or "{}")
    return {key: context.get(key) for key in _STATE_KEYS if key in context}


async def _save_state(database: DatabasePort, loan_id: str, state: dict | None) -> None:
    if not state:
        return
    row = await database.fetch_one(
        "SELECT context_json FROM loan_requests WHERE id = ?", (loan_id,)
    )
    context = json.loads(row["context_json"] or "{}") if row else {}
    for key in _STATE_KEYS:
        if key in state:
            context[key] = state[key]
    await database.execute(
        "UPDATE loan_requests SET context_json = ?, updated_at = ? WHERE id = ?",
        (json.dumps(context, ensure_ascii=False), now_iso(), loan_id),
    )


@router.post("/greeting")
async def greeting(
    payload: LoansGreetingRequest,
    database: DatabasePort = Depends(get_database),
    toolbox: Toolbox = Depends(get_toolbox),
    loans: LoansConsultService = Depends(get_loans_service),
) -> Response:
    session_id = "sess_" + uuid.uuid4().hex[:12]
    now = now_iso()
    await database.execute(
        "INSERT INTO sessions (id, user_id, active_surface_id, context_json, created_at, updated_at) "
        "VALUES (?,?,?,?,?,?)",
        (session_id, payload.user_id, None, "{}", now, now),
    )
    result = await loans.greeting(user_id=payload.user_id)
    audio = await _audio_bytes(toolbox, result.get("audio_id"))
    return _multipart({"session_id": session_id, **result}, audio, filename="greeting.mp3")


@router.post("/consult")
async def consult(
    payload: LoansConsultRequest,
    database: DatabasePort = Depends(get_database),
    toolbox: Toolbox = Depends(get_toolbox),
    loans: LoansConsultService = Depends(get_loans_service),
) -> Response:
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
            return _multipart(
                {
                    "status": "error",
                    "error_code": "transcription_failed",
                    "retryable": True,
                    "message": "; ".join(issues),
                },
                None,
            )
        text = transcription.get("text")
    if not text:
        return _multipart(
            {"status": "error", "error_code": "bad_request", "message": "text or audio is required"},
            None,
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
    state = await _load_state(database, loan_id)
    result = await loans.consult(
        user_id=user_id, text=text, loan_request_id=loan_id, history=history, state=state
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
        await _save_state(database, loan_id, result.get("state"))
        if result.get("terminal_response"):
            await database.execute(
                "UPDATE loan_requests SET status = 'terminal', updated_at = ? WHERE id = ?",
                (now_iso(), loan_id),
            )
    audio = await _audio_bytes(toolbox, result.get("audio_id"))
    return _multipart(dict(result), audio)


@router.get("", response_model=LoansListResponse)
async def list_loans(
    user_id: str = Query(default="u_ana"),
    database: DatabasePort = Depends(get_database),
    toolbox: Toolbox = Depends(get_toolbox),
) -> LoansListResponse:
    """All of the user's credits in one list: created loans + active liabilities."""
    return LoansListResponse(items=await _list_items(database, toolbox, user_id))


@router.post("", response_model=LoanResponse)
async def create_loan(
    payload: LoansCreateRequest,
    database: DatabasePort = Depends(get_database),
    toolbox: Toolbox = Depends(get_toolbox),
) -> LoanResponse:
    """Create the offered loan and disburse it. Called only when the user accepts."""
    purpose = payload.purpose
    purpose_private = bool(payload.purpose_private)
    if payload.loan_request_id:
        state = await _load_state(database, payload.loan_request_id)
        if not purpose and state.get("purpose"):
            purpose = str(state["purpose"])
        purpose_private = purpose_private or bool(state.get("purpose_private"))
    result = await toolbox.call(
        "create_loan",
        {
            "user_id": payload.user_id,
            "amount": payload.amount,
            "term_months": payload.months,
            "loan_request_id": payload.loan_request_id or "",
            "purpose": purpose or "",
            "purpose_private": purpose_private,
        },
    )
    if result.get("status") != "ok":
        raise HTTPException(
            status_code=400,
            detail="; ".join(result.get("issues", ["no se pudo crear el crédito"])),
        )
    return LoanResponse(status="ok", loan=result.get("loan"))


@router.get("/{loan_id}/ui", response_model=LoanDetailResponse)
async def get_loan_ui(
    loan_id: str,
    user_id: str = Query(default="u_ana"),
    service=Depends(get_loan_detail_service),
) -> LoanDetailResponse:
    """Personalized per-loan A2UI page: hydrate the stored template or build it once."""
    result = await service.get_or_create(user_id=user_id, entity="loan", entity_id=loan_id)
    if result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="unknown loan")
    if result.get("status") != "ok":
        raise HTTPException(
            status_code=400, detail=result.get("message", "no se pudo generar la página del crédito")
        )
    return LoanDetailResponse(
        status="ok",
        entity="loan",
        entity_id=loan_id,
        source=result.get("source"),
        catalog_id=result.get("catalog_id"),
        surface_id=result.get("surface_id"),
        a2ui=result.get("a2ui", []),
        audio_ref=result.get("audio_ref"),
    )


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
            a2ui = hydrated.get("a2ui", [])
            data_model: dict = {}
            for message in a2ui:
                if isinstance(message, dict) and "updateDataModel" in message:
                    data_model = message["updateDataModel"].get("value") or {}
                    break
            from agent.loans import resolve_loan_bindings

            a2ui = resolve_loan_bindings(a2ui, data_model)
            terminal = {
                "catalog_id": hydrated.get("catalog_id"),
                "surface_id": surface["id"],
                "a2ui": a2ui,
            }
    return LoansConsultResponse(
        status="ok",
        loan_request_id=loan_request_id,
        terminal_response=terminal,
        audio_ref=audio_ref,
    )
