"""GET /api/accounts, GET /api/liabilities, POST /api/liabilities/{id}/payment.

Plain REST reads/writes for native app screens that render their own UI
(inicio, prestamos) rather than a generated A2UI surface. Still goes through
MCP (INV-014) so the agent and these screens share one source of truth.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from mcp_servers.toolbox import Toolbox

from ..dependencies import get_toolbox
from ..schemas import (
    AccountsResponse,
    LiabilitiesResponse,
    PaymentRequest,
    PaymentResponse,
    ProfileResponse,
    RecipientCreateRequest,
    RecipientResponse,
    RecipientsResponse,
    TransferRequest,
    TransferResponse,
)

router = APIRouter(prefix="/api", tags=["finance"])


@router.get("/profile", response_model=ProfileResponse)
async def get_profile(
    user_id: str = Query(default="u_ana"), toolbox: Toolbox = Depends(get_toolbox)
) -> ProfileResponse:
    result = await toolbox.call("get_profile", {"user_id": user_id})
    if result.get("profile") is None:
        raise HTTPException(status_code=404, detail="unknown user")
    return ProfileResponse(profile=result["profile"])


@router.get("/accounts", response_model=AccountsResponse)
async def get_accounts(
    user_id: str = Query(default="u_ana"), toolbox: Toolbox = Depends(get_toolbox)
) -> AccountsResponse:
    result = await toolbox.call("get_accounts", {"user_id": user_id})
    return AccountsResponse(accounts=result.get("accounts", []))


@router.get("/liabilities", response_model=LiabilitiesResponse)
async def get_liabilities(
    user_id: str = Query(default="u_ana"), toolbox: Toolbox = Depends(get_toolbox)
) -> LiabilitiesResponse:
    result = await toolbox.call("get_liabilities", {"user_id": user_id})
    return LiabilitiesResponse(
        liabilities=result.get("liabilities", []),
        total_debt=result.get("totalDebt", 0.0),
        total_min_payment=result.get("totalMinPayment", 0.0),
    )


@router.post("/liabilities/{liability_id}/payment", response_model=PaymentResponse)
async def pay_liability(
    liability_id: str,
    payload: PaymentRequest,
    toolbox: Toolbox = Depends(get_toolbox),
) -> PaymentResponse:
    result = await toolbox.call(
        "make_payment",
        {
            "user_id": payload.user_id,
            "liability_id": liability_id,
            "amount": payload.amount,
            "account_id": payload.account_id,
        },
    )
    if result.get("status") != "ok":
        raise HTTPException(
            status_code=400, detail="; ".join(result.get("issues", ["payment failed"]))
        )
    return PaymentResponse(
        status=result["status"],
        applied_amount=result.get("appliedAmount", 0.0),
        liability=result.get("liability"),
        account=result.get("account"),
        transaction=result.get("transaction"),
        issues=result.get("issues", []),
    )


@router.get("/recipients", response_model=RecipientsResponse)
async def get_recipients(
    user_id: str = Query(default="u_ana"), toolbox: Toolbox = Depends(get_toolbox)
) -> RecipientsResponse:
    result = await toolbox.call("list_recipients", {"user_id": user_id})
    return RecipientsResponse(recipients=result.get("recipients", []))


@router.post("/recipients", response_model=RecipientResponse)
async def create_recipient(
    payload: RecipientCreateRequest,
    toolbox: Toolbox = Depends(get_toolbox),
) -> RecipientResponse:
    result = await toolbox.call(
        "create_recipient",
        {
            "user_id": payload.user_id,
            "alias": payload.alias,
            "clabe": payload.clabe,
            "bank_name": payload.bank_name,
        },
    )
    if result.get("status") != "ok":
        raise HTTPException(
            status_code=400, detail="; ".join(result.get("issues", ["could not save recipient"]))
        )
    return RecipientResponse(
        status=result["status"], recipient=result.get("recipient"), issues=result.get("issues", [])
    )


@router.post("/transfers", response_model=TransferResponse)
async def submit_transfer(
    payload: TransferRequest,
    toolbox: Toolbox = Depends(get_toolbox),
) -> TransferResponse:
    result = await toolbox.call(
        "transfer_funds",
        {
            "user_id": payload.user_id,
            "source_account_id": payload.source_account_id,
            "amount": payload.amount,
            "memo": payload.memo,
            "destination": payload.destination.model_dump(),
        },
    )
    if result.get("status") != "ok":
        raise HTTPException(
            status_code=400, detail="; ".join(result.get("issues", ["transfer failed"]))
        )
    return TransferResponse(
        status=result["status"],
        transfer=result.get("transfer"),
        source_account=result.get("sourceAccount"),
        destination_account=result.get("destinationAccount"),
        saved_recipient=result.get("savedRecipient"),
        issues=result.get("issues", []),
    )
