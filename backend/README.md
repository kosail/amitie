# La Mesa — Backend

Backend for **La Mesa**, an agent-driven financial application built for a bank
hackathon in Mexico. The agent decides which interface the user needs and
generates it in real time with **A2UI**; data, models, and actions are exposed
through **MCP**; the LLM sits at the center of the experience.

The backend runs **entirely locally** on a **local SQLite** database and is
exposed to the internet through a **Cloudflare Tunnel**. No remote database, no
cloud runtime.

> Source-of-truth documents live at the repository root:
> `INVARIANTS.md` (highest authority) > `SPECS.md` > `A2UI_CATALOG.md` > `AGENTS.md`.
> `CHANGELOG.md` is the append-only record of design decisions.

---

## 1. What it does

Two product pillars:

1. **La Mesa + El Revés (core).** The user describes a debt situation; the agent
   retrieves their real financial picture through MCP, chooses a restructuring
   strategy, asks the genuine tradeoff question, detects that the plan breaks,
   rebuilds the interface, and then negotiates on the user's behalf against a
   bank persona.
2. **Saving Bags (secondary).** The user names a goal (e.g. "viaje a Japón"); the
   agent infers clarifying questions, researches real average costs, compares
   them to the stated goal, and produces a dated plan grounded in the user's
   actual cash flow.

Plus automatic accessibility (**Voz y Color**), transparency (**Caja de Cristal**),
and the **Kill Test** proving the experience collapses without the LLM.

---

## 2. Architecture

```
            ┌─────────────────────────────────────────────────────────┐
            │              Frontend (separate team)                    │
            │        React + TypeScript + Tailwind, custom A2UI        │
            └───────────────────────────┬─────────────────────────────┘
                                        │  REST/JSON, full A2UI arrays
                                        │  (exposed via Cloudflare Tunnel)
            ┌───────────────────────────▼─────────────────────────────┐
            │               Backend (this repo, local)                 │
            │                                                          │
            │   FastAPI ──▶ Agent orchestrator (Gemini / ADK)          │
            │      │              │                                    │
            │      │              ├── MCP servers (in-process)         │
            │      │              │     finance · savings · ui · voice │
            │      │              └── providers (LLM/TTS/STT, failover)│
            │      │                                                   │
            │      ├── engine/        deterministic financial math     │
            │      ├── hydration/     placeholder hydration (planned)  │
            │      ├── observability/ trace ids, logs, traces table    │
            │      └── db/            persistence port → local SQLite  │
            └──────────────────────────────────────────────────────────┘
```

Data never leaves the host: the tunnel only forwards HTTP to the local process
(`INV-019`, `INV-020`).

---

## 3. Stack

**Implemented**
- Python 3.11+ (developed on 3.14), full type hints.
- SQLite via the stdlib `sqlite3` module, behind a narrow `DatabasePort`.
- Deterministic engine modules (pure functions, no IO).
- Provider layer: Gemini primary via `google-genai`, DeepSeek fallback via `httpx2`,
  with env-only selection and an automatic failover chain.

**Planned / in progress**
- FastAPI + Uvicorn for the HTTP API.
- Google ADK for agent orchestration.
- A2UI Python agent SDK for schema validation (`a2ui-agent-sdk`).
- MCP Python SDK for in-process `finance`, `savings`, `ui`, and `voice` servers.
- ElevenLabs TTS (fallback edge-tts); Gemini STT (fallback faster-whisper).
- `cloudflared` for internet exposure.

**Not ours**
- Frontend: React + TypeScript + Tailwind with a fully custom A2UI renderer.
  **No third-party UI component libraries.**

---

## 4. Repository structure

```
backend/
  config.py                 Settings loaded from .env (DATABASE_PATH, DEMO_MODE, LOG_LEVEL)
  requirements.txt          Python dependencies
  .env / .env.example       Local configuration and secrets (real .env is git-ignored)
  data/                     Local SQLite file lives here (git-ignored)

  db/                       Persistence layer (implemented)
    port.py                 DatabasePort protocol + DatabaseError
    local_sqlite.py         LocalSQLiteDatabase (stdlib sqlite3, async wrapper)
    schema.sql              Single source of truth for the schema (18 tables + indexes)
    schema.py               Load + apply schema
    seed.py                 Deterministic mock seed (fixed timestamps + RNG seed)
    sql_utils.py            SQL statement splitting
    init.py                 `python -m db.init` — create + seed the database

  engine/                   Deterministic financial math (implemented; INV-015)
    amortization.py         simulate(), strategies, per-month snapshots
    break_detection.py      detect_plan_breaks() → first negative-cash month
    feasibility.py          project_completion(), compute_feasibility(), capacity
    planning.py             context → engine adapter + plan/break payloads (M4)
    offer.py                lender-policy offer generation + feasibility (M5)

  observability/            Traceability (implemented; INV-018)
    context.py              Per-request trace id via contextvars
    tracing.py              Tracer persisting events to the `traces` table
    logging.py              Structured JSON logging carrying the trace id
    middleware.py           Framework-agnostic ASGI trace middleware

  providers/                Provider layer (implemented; INV-012, INV-013)
    base.py                 Normalized types + error taxonomy + LLMProvider protocol
    gemini.py               Primary LLM via google-genai
    deepseek.py             Fallback LLM via OpenAI-compatible httpx2
    registry.py             Env-only provider selection
    gateway.py              FallbackLLM: failover + cooldown + tracing

  ui_contract/              A2UI interface contract (implemented; M3.1)
    catalog.json            Machine-readable catalog (amitie.standard.v1)
    catalog.schema.json     SDK-format catalog (flat v0.9) for jsonschema validation
    catalog.py              Catalog loader (component specs, actions, messages)
    prompt.py               System-prompt generation from the catalog
    validator.py            JsonschemaValidator + CatalogValidator (semantic pass)
    schema_registry.py      referencing.Registry over the vendored A2UI schemas
    schemas/0.9/            vendored A2UI server_to_client.json + common_types.json

  hydration/                Data hydration (implemented; M3.2/M4)
    placeholders.py         Pure {{path}} resolve()/collect()
    service.py              revalidate(): canonical plan-section + BreakAlert (M4)

  mcp_servers/              In-process MCP servers (implemented; M3.2)
    toolbox.py              Toolbox over in-memory mcp.Client + result normalization
    finance/                get_profile, get_liabilities, get_income_streams,
                            get_subscriptions, get_cash_flow, get_financial_context,
                            simulate_plan, detect_plan_breaks,
                            get_lender_policies, generate_offer, evaluate_offer, accept_offer
    ui/                     persist_ui, hydrate_ui, a2ui_action,
                            record_negotiation_round, get_negotiation,
                            get_session, set_session_context
    # savings/, voice/ planned

  agent/                    ADK orchestration (implemented; M3.3/M5)
    model.py                GatewayLlm(BaseLlm) -> provider gateway + usage mapping
    tools.py                McpTool(BaseTool) wrappers over the MCP toolbox
    service.py              AgentService: persistent ADK sessions + run_turn
    negotiation.py          NegotiationService: bank/advocate personas, take-control, accept

  api/                      FastAPI HTTP API (implemented; M3.4)
    app.py                  create_app(): lifespan, CORS, TraceMiddleware, routers
    main.py                 uvicorn entrypoint (`uvicorn api.main:app`)
    dependencies.py         Depends() accessors over app.state
    schemas.py              Pydantic request/response models
    routers/                session, message, action, ui, negotiation, debug

  tests/                    Unit tests (stdlib unittest)
    test_local_sqlite.py    Schema + seed + queries
    test_schema.py          All required tables present
    test_seed.py            Seed determinism and coverage
    test_engine.py          Amortization, break detection, feasibility
    test_observability.py   Trace context, tracer, JSON logging, ASGI middleware
    test_providers.py       Failover, cooldown, tracing, DeepSeek + Gemini mapping
    test_a2ui_catalog.py    Catalog parity, payload validation, prompt generation
    test_a2ui_schema_validation.py  jsonschema validation against the A2UI SDK schemas
    test_toolbox.py         In-memory MCP toolbox list/call + result normalization
    test_finance_tools.py   Finance reads over the seeded database
    test_ui_tools.py        persist/hydrate/action + data freshness
    test_hydration.py       Placeholder resolution
    test_agent_model.py     GatewayLlm message/tool/usage mapping + call limit
    test_agent_tools.py     MCP tools wrapped as ADK tools
    test_agent_service.py   Turn persistence, sessions, error paths
    test_api.py             Full HTTP loop over TestClient (network-free)
    test_m3_acceptance.py   M3 acceptance: debt intent -> surface -> action -> regen
    test_planning.py        Context->engine adapter + plan/break payloads
    test_finance_plan_tools.py  simulate_plan + detect_plan_breaks
    test_revalidation.py    BreakAlert insert/remove + version bump (idempotent)
    test_m4_acceptance.py   M4 acceptance: BreakAlert mutation -> repair
    test_offer_engine.py    Offer generation + feasibility
    test_offer_tools.py     Offer MCP tools over the seeded database
    test_negotiation_service.py  Personas, rounds, take-control
    test_m5_acceptance.py   M5 acceptance: negotiation -> take-control -> accept

  # Planned directories (not created yet):
  # audio_cache/  pre-warmed TTS assets
  # demo/         DEMO_MODE, golden-path seed, rehearsal harness
```

Root documents (one level up): `AGENTS.md`, `INVARIANTS.md`, `SPECS.md`,
`CHANGELOG.md`, `A2UI_CATALOG.md`.

---

## 5. Initialize and run

From the `backend/` directory:

```sh
# 1. Activate the virtualenv (already present at backend/.venv)
source .venv/bin/activate

#    If it does not exist:
#    python -m venv .venv && source .venv/bin/activate

# 2. Install dependencies
python -m pip install -r requirements.txt

# 3. Create and seed the local database  ->  ./data/amitie.sqlite3
python -m db.init

# 4. Run the test suite (62 tests expected to pass)
python -m unittest discover -s tests -t . -v
```

`python -m db.init` is idempotent (schema uses `IF NOT EXISTS`; the seed clears
and rebuilds the showcase tables). Pass `--path` to target another file.

### Run the API and expose it

```sh
# terminal 1: run the API locally
uvicorn api.main:app --host 127.0.0.1 --port 8000

# terminal 2: expose it to the internet
cloudflared tunnel --url http://localhost:8000
```

Endpoints: `POST /api/session`, `POST /api/message`, `POST /api/action`,
`GET /api/ui/{surface_id}`, `GET /debug/trace/{trace_id}`, `GET /healthz`.

---

## 6. Configuration (`.env`)

Copy `.env.example` to `.env` and fill in. The real `.env` is git-ignored and
must never be committed (`INV-040`).

| Variable | Purpose |
|---|---|
| `DATABASE_PATH` | SQLite file path (default `./data/amitie.sqlite3`) |
| `DEMO_MODE` | Pins the system to seeded data / cached responses |
| `LOG_LEVEL` | Log verbosity |
| `AGENT_MAX_MODEL_CALLS` | Per-turn model-call budget (default 6) |
| `GEMINI_API_KEY` | Primary LLM (and STT / research grounding) |
| `DEEPSEEK_API_KEY` | Fallback LLM |
| `ELEVENLABS_API_KEY` | Primary text-to-speech |
| `LLM_PROVIDER` / `LLM_FALLBACK` | e.g. `gemini` / `deepseek` |
| `STT_PROVIDER` / `STT_FALLBACK` | e.g. `gemini` / `faster_whisper` |
| `TTS_PROVIDER` / `TTS_FALLBACK` | e.g. `elevenlabs` / `edge_tts` |
| `GEMINI_MODEL`, `DEEPSEEK_BASE_URL`, `DEEPSEEK_MODEL` | Model selection |
| `ELEVENLABS_VOICE_ID`, `ELEVENLABS_MODEL` | Voice selection |

Provider selection is environment-only; switching is a config change with no
code edits (`INV-013`).

> Security: any key disclosed outside `.env` is considered compromised and must
> be rotated after the event (`INV-041`).

---

## 7. Current status

**Milestones 1–2 and all of M3, M4, and M5 are complete.** Persistence,
deterministic engines, observability, the LLM provider layer with failover, the
A2UI contract and SDK-schema validation, in-process MCP servers, hydration, the
ADK agent, the FastAPI HTTP API, the La Mesa mutations (`simulate_plan`,
proactive `BreakAlert`, repair, deterministic revalidation), and El Revés
(bank/advocate personas, take-control, simulated acceptance) are implemented and
covered by tests.

| Layer | Status |
|---|---|
| Persistence port + local SQLite | ✅ Implemented, tested |
| Schema (18 tables) + deterministic seed | ✅ Implemented, tested |
| `python -m db.init` CLI | ✅ Implemented |
| Engine (amortization, breaks, feasibility) | ✅ Implemented, tested |
| Observability (trace id, logging, traces table, ASGI middleware) | ✅ Implemented, tested |
| Provider layer — LLM (Gemini → DeepSeek failover) | ✅ Implemented, tested |
| A2UI catalog + prompt + validator (M3.1) | ✅ Implemented, tested |
| A2UI SDK-schema validation (`jsonschema`) | ✅ Implemented, tested |
| MCP servers — finance + ui (in-process) | ✅ Implemented, tested |
| Hydration (placeholders + fresh data) | ✅ Implemented, tested |
| ADK agent orchestrator (M3.3) | ✅ Implemented, tested |
| FastAPI HTTP API (M3.4) | ✅ Implemented, tested |
| La Mesa mutations (`BreakAlert`, repair) (M4) | ✅ Implemented, tested |
| Structural revalidation (deterministic) | ✅ Implemented, tested |
| El Revés negotiation (M5) | ✅ Implemented, tested |
| Saving Bags | ⏳ Planned (M6) |
| Voz y Color (accessibility + voice) | ⏳ Planned (M7) |
| Caja de Cristal + Kill Test + DEMO_MODE | ⏳ Planned (M8) |

**Test suite:** 85 tests, all passing.

### Roadmap
1. **M6** — Saving Bags (goal creation, grounded research, feasibility, polling).
2. **M7–M8** — Voz y Color, Caja de Cristal + Kill Test.

---

## 8. Conventions

- Read `INVARIANTS.md` before changing anything; it outranks every other document.
- The LLM never computes financial math — use `engine/` (`INV-015`).
- All data access goes through the persistence port / MCP; never touch SQLite directly.
- Every request carries a `trace_id`; every LLM and MCP call is recorded (`INV-018`).
- Every meaningful change gets an appended `CHANGELOG.md` entry.
- Generated interfaces may only use components from `A2UI_CATALOG.md`.
