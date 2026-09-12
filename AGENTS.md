# AGENTS.md — Project Context & Operating Rules

> **This file is the operating manual for humans and AI agents working on this repository.**
> It describes *what the project is*, *what stack we use*, and *how work must be done*.
>
> It does **not** contain core architecture decisions or business requirements.
> - Core, non-negotiable decisions → `INVARIANTS.md`
> - Business requirements → `SPECS.md`
> - Machine-readable change history → `CHANGELOG.md`
>
> **Authority order:** `INVARIANTS.md` > `SPECS.md` > `AGENTS.md`.

---

## 1. What this project is

**La Mesa** is an AI-agent-driven financial application built for a bank hackathon in Mexico. The agent, not a fixed application, decides what interface the user needs and generates it in real time. Interfaces are described with **A2UI** and delivered as JSON; data and actions are exposed through **MCP**; the LLM is the center of the experience.

Two product pillars:

1. **La Mesa + El Revés (core).** The user describes a debt situation; the agent retrieves their real financial picture through MCP, chooses a restructuring strategy, asks the genuine tradeoff question, **detects that the plan breaks**, rebuilds the interface, and then negotiates on the user's behalf against a bank persona.
2. **Saving Bags (secondary).** The user names a goal (e.g. "viaje a Japón"); the agent infers clarifying questions, researches real average costs, compares them to the user's stated goal, and produces a dated plan grounded in the user's actual (mocked) cash flow. It offers the user loans (redirecting the user to La Mesa) to complete the goal based on specific situation (like almost reaching the deadline or the user wanting to reduce the previously set goal).

Plus automatic accessibility (`Voz y Color`), transparency (`Caja de Cristal`), and the `Kill Test` that proves the experience collapses without the LLM.

The financial problem must be genuine. Avoid the generic, predictable ideas this hackathon explicitly warns against (see §2).

---

## 2. Hackathon context (external, fixed)

- **Challenge:** AI agents that generate interfaces in real time for an open financial-services use case. **MCP is required. A2UI is mandatory and non-negotiable.**
- **The LLM must be central:** it interprets intent, reasons about context, makes decisions, orchestrates tools, and determines the interface. It cannot be an ornamental chatbot on a conventional app.
- **MCP must be architecturally meaningful:** it provides data, tools, actions, and the data models of the solution. It must not exist to satisfy a checklist.
- **A2UI represents and transmits the interface.** The generated interface must be a consequence of the agent's reasoning, not a collection of predetermined screens.
- **Judging priority (optimize in this exact order):**
  1. Fulfillment and usefulness for the user
  2. Quality and adaptability of the generated UI
  3. Quality of the AI solution
  4. Architecture and engineering
  5. UX and design
  6. Innovation
  7. Presentation, pitch, and showcase
- **Targeting zones:** Personal Banking, Investments, Loans and Credits, Payments, Insurance, Financial Education. This project lives primarily in **Loans and Credits** and **Personal Banking / Financial Education**.
- **Data:** synthetic, simulated, or public. Data realism matters less than idea quality, usefulness, agent behavior, generated UI, and the interaction loop.
- **MVP constraints:** 4 developers, ~24 working hours over 3 days. Languages available: React + TypeScript, C++, Java, Kotlin + Compose Multiplatform, Python. Prefer mocked infrastructure. Do not build auth, production databases, deployment infrastructure, complex microservices, elaborate analytics, native mobile apps, payment rails, or enterprise security. The backend is exposed to the internet through a **Cloudflare Tunnel** only; all data and processing remain local. This is not a production database or cloud-deployment integration and does not violate this constraint.

### Forbidden patterns
Do not build static reports, static dashboards, one-shot generated pages, predetermined screens disguised as generated UI, read-only visualizations, LLM responses that merely populate a fixed frontend, or a chatbot followed by a conventional application. If removing the LLM leaves essentially the same UI and workflow, the architecture is wrong.

### Anti-fluff rule
Never describe work as innovative, revolutionary, disruptive, personalized, intelligent, agentic, or adaptive unless the implementation provides concrete evidence. Replace adjectives with observable behavior.

---

## 3. Stack

**Backend (owned by this repository):**
- Python 3.11+, type hints throughout.
- FastAPI + Uvicorn for the HTTP API.
- Google ADK for agent orchestration.
- A2UI Python agent SDK (`a2ui-agent-sdk`) for schema management and validation.
- Python MCP SDK for the `finance`, `savings`, `ui`, and `voice` MCP servers.
- Persistence is a single local **SQLite** database (stdlib `sqlite3`) reached through a narrow persistence port (`INV-019`). No ORM, no remote or managed database.
- The local backend is exposed to the internet with a **Cloudflare Tunnel** (`cloudflared`); no Cloudflare database or Workers runtime is used.
- `httpx` for outbound HTTP.
- **LLM:** Gemini (Google AI Studio / ADK) primary; DeepSeek (OpenAI-compatible) fallback.
- **TTS:** ElevenLabs primary; edge-tts fallback.
- **STT:** Gemini multimodal primary; faster-whisper fallback.

**Frontend (owned by the frontend team, not this repository's backend scope):**
- React + TypeScript + Tailwind CSS.
- Custom A2UI catalog and renderer. **No third-party component libraries** (no MUI, shadcn/ui, Chakra, Ant Design, etc.).
- Consumes only the frozen REST contract in `SPECS.md` §8.

---

## 4. Repository layout

Root documents: `AGENTS.md`, `INVARIANTS.md`, `SPECS.md`, `CHANGELOG.md`, and `A2UI_CATALOG.md` (the frozen backend/frontend interface contract).

```
/backend
  api/            FastAPI app factory, lifespan, DI, routers (session, message, action, ui, debug)
  agent/          ADK orchestrator: model.py (GatewayLlm), tools.py (MCP->ADK), service.py, negotiation.py (El Reves)
  providers/      base interfaces + gemini, deepseek, elevenlabs, edge_tts, faster_whisper, registry
  ui_contract/    catalog.json + catalog.schema.json + prompt.py + validator.py + vendored A2UI schemas
  mcp_servers/    in-process MCP servers (named to avoid shadowing the `mcp` SDK)
    finance/      liabilities, income, subscriptions, cash flow, context
    ui/           persist, hydrate, a2ui_action, negotiation rounds + session context
    toolbox.py    Toolbox over in-memory mcp.Client + result normalization
    # savings/, voice/ planned
  engine/         deterministic amortization, break detection, feasibility, planning adapter (pure, tested)
  hydration/      placeholder resolver + revalidation hook (pure, tested)
  db/             port.py, local_sqlite.py, schema.sql, schema.py, seed.py, sql_utils.py, init.py
  tests/          persistence, engine, observability, provider, and A2UI contract tests
  observability/  trace middleware, structured logging, /debug/trace
  audio_cache/    pre-warmed TTS assets
  demo/           DEMO_MODE, golden-path seed, rehearsal harness
  .env.example    template only; real .env is git-ignored
```

Every MCP server has its own entrypoint and can be started, stopped, and tested independently.

---

## 5. Rules of operation for agents

1. **Read `INVARIANTS.md` before any change.** If a task would violate an invariant, stop and propose an invariant change instead of working around it.
2. **Append to `CHANGELOG.md`** for every meaningful change, decision, or fix. The changelog is append-only and written for future agents.
3. **Never silently change an invariant.** Invariant changes require explicit human approval and a changelog entry with rationale (see `INVARIANTS.md` §F).
4. **Keep the system modular.** New capabilities go behind an interface; do not couple the orchestrator to a specific provider, database call, or transport. Provider selection is env-only.
5. **MCP is the only door to data and actions.** Do not bypass the persistence port or touch SQLite directly from the agent or API layers; go through MCP.
6. **Never compute financial math in the LLM or in prompt logic.** Use `engine/`.
7. **Never deliver stale data.** Hydrate immediately before every response; revalidate structure when context may have changed.
8. **Prefer the smallest system that proves the thesis.** One extraordinary interaction over ten mediocre features.
9. **Do not commit, push, or open PRs unless explicitly asked.**
10. **Do not add secrets anywhere except `.env`.** See §8.

---

## 6. Code style

- **Python:** PEP 8, full type hints, small pure functions in `engine/` and `hydration/`, dependency injection over globals. Pydantic models at all boundaries (HTTP, MCP, providers). `async` for IO, synchronous pure functions for computation.
- **Naming:** `snake_case` for Python, stable `REQ-*` IDs from `SPECS.md` in tests and commits.
- **Errors:** typed exceptions; the provider failover chain reacts to quota, rate-limit, timeout, and validation errors.
- **Logging:** structured logging only. Never `print`. Never log secrets, raw audio, or full financial payloads.
- **Comments:** code should be self-documenting. Add a comment only when the *why* is non-obvious; do not narrate the *what*.
- **TypeScript/frontend (if touched):** strict mode, functional components, Tailwind utilities, custom primitives. No component libraries.
- **Formatting:** keep modules small and single-purpose; a file that needs scrolling to understand is a signal to split it.

---

## 7. Documentation-fetching rules

**Never guess an API, tool name, parameter, message shape, or provider behavior. Fetch the primary source first.**

Required sources, in priority order:

| Area | Source |
|---|---|
| A2UI protocol, catalogs, actions, MCP integration | https://a2ui.org/ (and its specification pages) |
| A2UI source / renderers / agent SDK | https://github.com/a2ui-project/a2ui |
| Model Context Protocol | https://modelcontextprotocol.io/ |
| Google ADK | https://google.github.io/adk-docs/ |
| Gemini API (text, multimodal, grounding) | https://ai.google.dev/gemini-api/docs |
| ElevenLabs API | https://elevenlabs.io/docs |
| FastAPI | https://fastapi.tiangolo.com/ |
| edge-tts | PyPI package documentation |
| faster-whisper | project repository documentation |
| Cloudflare Tunnel (`cloudflared`) | https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/ |

Rules:
1. Fetch the official page before implementing an integration; do not rely on memory.
2. Record the version or spec revision used when it affects behavior (e.g., A2UI v0.9.1 vs v1.0 candidate) in the `CHANGELOG.md` entry — not in code comments.
3. Do not upgrade a protocol version or provider SDK without human approval and a changelog entry.
4. Prefer protocol-native mechanisms (A2UI data binding, `a2ui_action`, MCP resources/tools) over custom reimplementations.

---

## 8. Secrets & security

- All credentials (`GEMINI_API_KEY`, `DEEPSEEK_API_KEY`, `ELEVENLABS_API_KEY`, etc.) live only in `backend/.env`. Runtime configuration (`DATABASE_PATH`, `DEMO_MODE`, `LOG_LEVEL`) also lives in `.env`.
- `.env` is git-ignored. `backend/.env.example` contains names and placeholders only.
- Never commit, log, echo, or document a secret. Never paste secrets into generated code.
- Any key disclosed outside `.env` is considered compromised and must be rotated after the event.
- Do not log raw audio or full financial payloads; log `trace_id` and metadata instead.

---

## 9. Testing & verification

- `pytest` for `engine/`, `hydration/`, and repository logic; deterministic and pure where possible.
- At least one acceptance test per `REQ-*` in `SPECS.md` for the golden path.
- A provider smoke test that asserts the failover chain activates on quota/rate-limit.
- A schema test asserting all required tables exist, and a seed test asserting the seed is deterministic and covers the showcase entities.
- Verify A2UI payloads with the A2UI agent SDK before they leave the backend.
- Run the golden path in `DEMO_MODE` before any rehearsal.
- When a task is complete, run the relevant tests and lint/type checks; if a check command is not yet defined, propose one and record it here.

---

## 10. Definition of done

A change is done when it:
1. satisfies or advances one or more `REQ-*` requirements,
2. violates no invariant,
3. is covered by a test or an explicit acceptance check,
4. keeps provider swaps env-only,
5. has an appended `CHANGELOG.md` entry describing the what, why, and impact,
6. leaves the golden path runnable end to end.

---

## 11. Runbook — local run & Cloudflare Tunnel

From `backend/`:

```sh
python -m venv .venv && . .venv/bin/activate
python -m pip install -r requirements.txt
python -m db.init                                  # create + seed ./data/amitie.sqlite3
python -m unittest discover -s tests -t .          # run backend tests
```

Expose the local backend to the internet through a Cloudflare Tunnel (no data leaves the host):

```sh
# once the FastAPI app exists and listens on 127.0.0.1:8000
cloudflared tunnel --url http://localhost:8000
```

The API and MCP servers are not implemented yet; until then the only runnable pieces are `python -m db.init` and the test suite.
