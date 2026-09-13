"""Finance MCP server (read-only tools)."""

from __future__ import annotations

from typing import Any

from db.port import DatabasePort
from mcp.server import MCPServer

from . import service


def build_finance_server(database: DatabasePort, settings: Any | None = None) -> MCPServer:
    if settings is None:
        from config import Settings

        settings = Settings()
    server = MCPServer("finance")

    @server.tool()
    async def get_profile(user_id: str) -> dict[str, Any]:
        """Return the user's profile and accessibility flags."""
        return {"profile": await service.get_profile(database, user_id)}

    @server.tool()
    async def get_audience(user_id: str) -> dict[str, Any]:
        """Return the user's audience level (simple/standard/detailed), derived from
        age, accessibility, education and real financial activity. The agent must
        adapt the interface complexity to this directive."""
        return {"audience": await service.get_audience(database, user_id)}

    @server.tool()
    async def get_liabilities(user_id: str) -> dict[str, Any]:
        """Return the user's liabilities with totals, ordered by balance descending."""
        items = await service.get_liabilities(database, user_id)
        return {
            "liabilities": items,
            "totalDebt": round(sum(item["balance"] for item in items), 2),
            "totalMinPayment": round(sum(item["minPayment"] for item in items), 2),
        }

    @server.tool()
    async def get_accounts(user_id: str) -> dict[str, Any]:
        """Return the user's accounts with their current balances."""
        return {"accounts": await service.get_accounts(database, user_id)}

    @server.tool()
    async def make_payment(
        user_id: str, liability_id: str, amount: float, account_id: str | None = None
    ) -> dict[str, Any]:
        """Apply a real payment ("abono") against a liability, moving funds out of an
        account and recording a transaction. Deterministic; the LLM never computes
        this math."""
        return await service.make_payment(
            database, user_id, liability_id, amount, account_id=account_id
        )

    @server.tool()
    async def list_recipients(user_id: str) -> dict[str, Any]:
        """Return the user's saved transfer recipients (alias, CLABE, bank)."""
        return {"recipients": await service.list_recipients(database, user_id)}

    @server.tool()
    async def create_recipient(
        user_id: str, alias: str, clabe: str, bank_name: str
    ) -> dict[str, Any]:
        """Save a new transfer recipient. Re-validates the CLABE checksum
        server-side; never trusts the client's validation alone."""
        return await service.create_recipient(database, user_id, alias, clabe, bank_name)

    @server.tool()
    async def transfer_funds(
        user_id: str,
        source_account_id: str,
        amount: float,
        memo: str,
        destination: dict[str, Any],
    ) -> dict[str, Any]:
        """Move real, persisted money out of the source account — to another
        of the user's own accounts (crediting it) or to an external CLABE
        recipient (source-only debit). Deterministic; the LLM never computes
        this math."""
        return await service.transfer_funds(
            database, user_id, source_account_id, amount, memo, destination
        )

    @server.tool()
    async def get_income_streams(user_id: str) -> dict[str, Any]:
        """Return the user's income streams."""
        return {"incomeStreams": await service.get_income_streams(database, user_id)}

    @server.tool()
    async def get_subscriptions(user_id: str) -> dict[str, Any]:
        """Return the user's subscriptions and their monthly total."""
        items = await service.get_subscriptions(database, user_id)
        return {
            "subscriptions": items,
            "subscriptionTotal": round(sum(item["amount"] for item in items), 2),
        }

    @server.tool()
    async def get_cash_flow(user_id: str, months: int = 6) -> dict[str, Any]:
        """Return monthly income/expense aggregates and the average surplus."""
        return {"cashFlow": await service.get_cash_flow(database, user_id, months)}

    @server.tool()
    async def get_financial_context(user_id: str) -> dict[str, Any]:
        """Return the full financial context used as the A2UI data model."""
        return {"context": await service.financial_context(database, user_id)}

    @server.tool()
    async def get_credit_history(user_id: str, months: int = 6) -> dict[str, Any]:
        """Return a compact credit history (credits, totals, cash flow, spending by
        category) for the loans consult prompt."""
        return {
            "creditHistory": await service.get_credit_history(database, user_id, months=months)
        }

    @server.tool()
    async def analyze_loans(user_id: str, strategy: str = "avalanche") -> dict[str, Any]:
        """Deterministic loan analysis: baseline vs accelerated scenarios, interest and
        months saved, payoff order, the user's behavior tendencies, quincena pressure and
        a next-best action. The model presents these numbers; it never computes them."""
        return {"analysis": await service.analyze_loans(database, user_id, strategy=strategy)}

    @server.tool()
    async def simulate_plan(
        user_id: str,
        strategy: str = "avalanche",
        extra_payment: float = 0.0,
        extra_income: float = 0.0,
        expense_reduction: float = 0.0,
        horizon_months: int = 36,
        events: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        """Deterministically simulate a debt plan and report any break. The model
        chooses the strategy and parameters; the engine computes every number."""
        return await service.simulate_plan(
            database,
            user_id,
            strategy=strategy,
            extra_payment=extra_payment,
            extra_income=extra_income,
            expense_reduction=expense_reduction,
            horizon_months=horizon_months,
            events=events,
        )

    @server.tool()
    async def detect_plan_breaks(
        user_id: str,
        strategy: str = "avalanche",
        extra_payment: float = 0.0,
        extra_income: float = 0.0,
        expense_reduction: float = 0.0,
        horizon_months: int = 36,
        events: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        """Report the first month the plan cannot be covered (if any)."""
        return await service.detect_plan_breaks(
            database,
            user_id,
            strategy=strategy,
            extra_payment=extra_payment,
            extra_income=extra_income,
            expense_reduction=expense_reduction,
            horizon_months=horizon_months,
            events=events,
        )

    @server.tool()
    async def get_lender_policies() -> dict[str, Any]:
        """Return the bank's negotiation policies (bounds the bank may offer within)."""
        return await service.get_lender_policies(database)

    @server.tool()
    async def generate_offer(
        user_id: str, creditor: str = "", strategy: str = "consolidation"
    ) -> dict[str, Any]:
        """Deterministically build an offer within the lender's policy bounds."""
        return await service.generate_offer(
            database, user_id, creditor=creditor or None, strategy=strategy
        )

    @server.tool()
    async def evaluate_offer(user_id: str, offer: dict[str, Any]) -> dict[str, Any]:
        """Check deterministically whether the user can actually pay an offer."""
        return await service.evaluate_offer(database, user_id, offer)

    @server.tool()
    async def accept_offer(user_id: str, offer: dict[str, Any]) -> dict[str, Any]:
        """Simulated acceptance of an offer; returns confirmation and next steps."""
        return await service.accept_offer(database, user_id, offer)

    @server.tool()
    async def compute_loan_offer(
        user_id: str, requested_amount: float = 0.0, requested_term: int = 0
    ) -> dict[str, Any]:
        """Deterministic loan offer: backend-proposed amount, amount-banded plazo
        options, IRR-based CAT, per-month schedule and the risk panel (DTI, surplus,
        buffer, relative cost, income stability, savings-goal impact, payment-history
        projection, warnings). Pass `requested_term` (months) to present the offer at
        a plazo the user asked for."""
        return {
            "offer": await service.compute_loan_offer(
                database,
                user_id,
                requested_amount=requested_amount or None,
                apr=settings.loan_default_apr,
                term_months=settings.loan_default_term_months,
                requested_term=requested_term or None,
                opening_fee_pct=settings.loan_opening_fee_pct,
                insurance_fee_pct=settings.loan_insurance_fee_pct,
                dti_cap=settings.loan_dti_cap,
            )
        }

    @server.tool()
    async def store_loan_offer(
        loan_request_id: str, user_id: str, offer: dict[str, Any]
    ) -> dict[str, Any]:
        """Persist the offer shown for a consult so acceptance can be validated."""
        return await service.store_loan_offer(
            database, loan_request_id=loan_request_id, user_id=user_id, offer=offer
        )

    @server.tool()
    async def create_loan(
        user_id: str,
        amount: float,
        term_months: int = 0,
        loan_request_id: str = "",
    ) -> dict[str, Any]:
        """Create the loan + disburse it (called only when the user accepts)."""
        return await service.create_loan(
            database,
            user_id,
            amount=amount,
            apr=settings.loan_default_apr,
            term_months=term_months,
            loan_request_id=loan_request_id or None,
        )

    return server
