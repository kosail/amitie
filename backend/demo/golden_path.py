"""Golden-path rehearsal runner (REQ-NFR-05, REQ-DEMO-01).

Drives a running La Mesa backend through the demo beats and reports per-step
timing. Usage (with the API already running on 127.0.0.1:8000):

    python -m demo.golden_path --base-url http://127.0.0.1:8000 --user u_ana

This is a rehearsal aid: the LLM decides the actual interfaces, so the runner
narrates and times the journey rather than asserting exact payloads. Run it in
`DEMO_MODE=1` before a live rehearsal (AGENTS.md §9).
"""

from __future__ import annotations

import argparse
import time
from typing import Any

import httpx2

BUDGET_SECONDS = 90


def _show(step: str, elapsed: float, detail: str) -> None:
    print(f"[{elapsed:6.2f}s] {step:<22} {detail}")


def run(base_url: str, user_id: str) -> int:
    client = httpx2.Client(base_url=base_url, timeout=120.0)
    started = time.perf_counter()
    surface_id: str | None = None
    session_id: str | None = None

    def step(name: str, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        nonlocal surface_id
        mark = time.perf_counter()
        response = client.request(method, path, **kwargs)
        elapsed = time.perf_counter() - started
        body = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
        if body.get("surface_id"):
            surface_id = body["surface_id"]
        _show(name, elapsed, f"{response.status_code} {body.get('status', '')}".strip())
        return body

    try:
        session = step("session", "POST", "/api/session", json={"user_id": user_id})
        session_id = session["session_id"]

        step("debt intent", "POST", "/api/message", json={"session_id": session_id, "text": "Tengo 5 deudas y ya no puedo"})
        if surface_id:
            step("break mutation", "GET", f"/api/ui/{surface_id}")

        step(
            "repair",
            "POST",
            "/api/action",
            json={
                "surface_id": surface_id,
                "name": "approve_plan",
                "source_component_id": "plan",
                "context": {"extra_income": 8000},
            },
        )

        step("el reves (bank)", "POST", f"/api/negotiation/{session_id}/turn", json={"user_id": user_id})
        step("el reves (advocate)", "POST", f"/api/negotiation/{session_id}/turn", json={"user_id": user_id})
        accepted = step(
            "accept offer",
            "POST",
            "/api/action",
            json={
                "surface_id": surface_id,
                "name": "accept_offer",
                "source_component_id": "offer",
                "context": {"session_id": session_id},
            },
        )

        kill_surface = accepted.get("surface_id") or surface_id
        if kill_surface:
            step("kill test", "GET", f"/debug/kill-test/{kill_surface}")

        total = time.perf_counter() - started
        status = "OK" if total <= BUDGET_SECONDS else "OVER BUDGET"
        print(f"\n{status}: golden path completed in {total:.2f}s (budget {BUDGET_SECONDS}s)")
        return 0 if total <= BUDGET_SECONDS else 1
    except Exception as exc:  # pragma: no cover - rehearsal aid
        print(f"golden path failed after {time.perf_counter() - started:.2f}s: {exc!r}")
        return 1
    finally:
        client.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the La Mesa golden path against a live backend.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--user", default="u_ana")
    args = parser.parse_args()
    raise SystemExit(run(args.base_url, args.user))


if __name__ == "__main__":
    main()
