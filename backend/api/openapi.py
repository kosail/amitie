"""OpenAPI metadata for the frozen REST contract (SPECS.md §8, INV-023).

The schema is served by FastAPI at `/openapi.json`. Swagger UI is at `/docs`.
"""

from __future__ import annotations

OPENAPI_DESCRIPTION = """
REST JSON contract for **La Mesa**. Every mutating response carries a full A2UI
message array. No WebSockets or SSE (INV-010).

Frozen routes live in `SPECS.md` §8 (`REQ-API-01` … `REQ-API-08`). The frontend
consumes this HTTP API only; LLM providers are not called from the client.

Interactive docs: `/swagger` or `/docs` (Swagger UI) and `/redoc`. Machine-readable spec:
`/openapi.json`.
""".strip()

OPENAPI_TAGS = [
    {"name": "session", "description": "Create a conversation session (`REQ-API-01`)."},
    {
        "name": "message",
        "description": "Send user text or audio to the agent (`REQ-API-02`).",
    },
    {
        "name": "action",
        "description": "Closed-loop A2UI action back to the agent (`REQ-API-03`).",
    },
    {
        "name": "ui",
        "description": "Hydrate a persisted surface with fresh data (`REQ-API-04`).",
    },
    {"name": "saving-bags", "description": "Saving Bags pillar (`REQ-API-05`)."},
    {"name": "negotiation", "description": "El Revés bank negotiation (`REQ-API-06`)."},
    {"name": "audio", "description": "Cached TTS bytes (`REQ-API-07`)."},
    {
        "name": "debug",
        "description": "Kill Test and traces (`REQ-API-08`). Not a product surface.",
    },
    {"name": "ops", "description": "Process health. Not part of the frozen product contract."},
]

# Paths the frontend (and generated OpenAPI clients) must be able to see.
FROZEN_OPENAPI_PATHS = (
    "/api/session",
    "/api/message",
    "/api/action",
    "/api/ui/{surface_id}",
    "/api/saving-bags",
    "/api/saving-bags/{bag_id}",
    "/api/saving-bags/{bag_id}/answer",
    "/api/saving-bags/{bag_id}/refresh",
    "/api/negotiation/{session_id}/turn",
    "/api/negotiation/{session_id}/take-control",
    "/api/audio/{asset_id}",
    "/debug/kill-test/{surface_id}",
    "/debug/trace/{trace_id}",
)


def generate_openapi_spec() -> dict:
    """Generate the complete OpenAPI 3.1 specification dictionary."""
    try:
        from .app import create_app
    except ImportError:
        from api.app import create_app

    app = create_app()
    return app.openapi()


def export_openapi(output_path: str | None = None, indent: int = 2) -> str:
    """Generate and optionally save the OpenAPI JSON specification."""
    import json
    from pathlib import Path

    spec = generate_openapi_spec()
    rendered = json.dumps(spec, indent=indent, ensure_ascii=False)
    if output_path:
        Path(output_path).write_text(rendered + "\n", encoding="utf-8")
    return rendered


if __name__ == "__main__":
    import argparse
    from pathlib import Path
    import sys

    # Ensure backend directory is on sys.path even when run directly as a script
    backend_dir = str(Path(__file__).resolve().parent.parent)
    if backend_dir not in sys.path:
        sys.path.insert(0, backend_dir)

    parser = argparse.ArgumentParser(description="Export La Mesa OpenAPI specification.")
    parser.add_argument(
        "--out",
        "-o",
        dest="output_path",
        default=None,
        help="Path to write the openapi.json file to (prints to stdout if omitted).",
    )
    parser.add_argument(
        "--indent",
        type=int,
        default=2,
        help="JSON indentation spaces (default: 2).",
    )
    args = parser.parse_args()

    content = export_openapi(output_path=args.output_path, indent=args.indent)
    if args.output_path:
        print(f"OpenAPI specification written to {args.output_path}", file=sys.stderr)
    else:
        print(content)


