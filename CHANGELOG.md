# CHANGELOG.md — Agent Decision & Change Log

> **Audience: AI agents.** This file is a machine-read, append-only record of every meaningful change and design decision made by AI agents working on this project.
>
> **Rules:**
> - **Append-only.** Never edit or delete a previous entry. Corrections are new entries.
> - **Newest entries go at the bottom** (chronological order).
> - One entry per meaningful change, decision, invariant change, or fix.
> - Keep entries factual and reconstruct the *why*, not just the *what*.
> - **Never record secret values.** Reference credential names only.
> - Invariant changes MUST appear here (see `INVARIANTS.md` §F).

## Entry schema

```
## [YYYY-MM-DD] <type> — <short title>
- agent: <agent/model identifier>
- requirements: <REQ-* ids touched, or "none">
- invariants: <INV-* ids affected, or "none">
- files: <paths created/changed>
- decision: <what was decided or changed>
- rationale: <why>
- impact: <consequences, dependencies, what is now unblocked/blocked>
- follow_ups: <next actions or open questions, or "none">
```

`type` ∈ `bootstrap | decision | change | fix | invariant-change | cut | risk`.

---

## [2026-09-12] bootstrap — Four-document source-of-truth established
- agent: opencode / deepseek-flash
- requirements: none
- invariants: none
- files: `AGENTS.md`, `INVARIANTS.md`, `SPECS.md`, `CHANGELOG.md`
- decision: Split project truth into four documents with strict separation of concerns: `AGENTS.md` (context, stack, operating/style/doc rules, external hackathon constraints), `INVARIANTS.md` (non-negotiable decisions; highest authority), `SPECS.md` (structured testable business requirements), `CHANGELOG.md` (this machine-readable append-only log).
- rationale: The team needs extreme modularity and fast repair/trace. Separating fixed truth from requirements from operating rules lets agents and humans locate the relevant source instantly and prevents silent architectural drift.
- impact: Authority order fixed as `INVARIANTS.md` > `SPECS.md` > `AGENTS.md`. `AGENTS.md` was rewritten from the original hackathon-rules document; hackathon constraints are preserved under §2, and architecture decisions were moved into `INVARIANTS.md`.
- follow_ups: Scaffold `/backend` per `AGENTS.md` §4 and satisfy `REQ-API-*` first.

## [2026-09-12] decision — Core product scope locked
- agent: opencode / deepseek-flash
- requirements: REQ-LM-01..09, REQ-BAG-01..08
- invariants: INV-001, INV-002, INV-005, INV-030
- files: `INVARIANTS.md`, `SPECS.md`
- decision: `La Mesa + El Revés` is the core feature; `Saving Bags` is the secondary core feature. Hard cut line: two La Mesa mutation moments, El Revés, one saving bag, one accessible persona.
- rationale: The bank judges usefulness first and rewards one extraordinary interaction over many features. The selected scope maximizes impact per engineering hour within ~24 hours across four developers.
- impact: All non-essential features are cut. Time budget is protected for the two mutation moments and the negotiation.
- follow_ups: Define the exact acceptance tests for REQ-LM-05, REQ-LM-06, REQ-LM-07.

## [2026-09-12] decision — Accessibility (Voz y Color) is automatic
- agent: opencode / deepseek-flash
- requirements: REQ-ACC-01..06
- invariants: INV-003
- files: `INVARIANTS.md`, `SPECS.md`
- decision: `Voz y Color` activates automatically from account flags (elderly, blind, other accessibility needs, low literacy). Fully duplex voice: TTS out via ElevenLabs, STT in via Gemini, with fallbacks. Audio cached by text hash.
- rationale: Automatic activation makes UI adaptability observable (judging criterion #2) and addresses a genuine financial-inclusion problem in Mexico rather than appearing as a gimmick.
- impact: Requires a second custom A2UI catalog (`voz-color`), a `voice` MCP server, an accessibility profile table, and audio caching.
- follow_ups: Coordinate catalog IDs and flags with the frontend team.

## [2026-09-12] decision — HTTP-only REST JSON transport
- agent: opencode / deepseek-flash
- requirements: REQ-API-01..08, REQ-LOOP-05
- invariants: INV-010
- files: `INVARIANTS.md`
- decision: Use plain HTTP REST JSON; each response carries the full A2UI message array. No WebSockets and no SSE. Bandwidth and streaming latency are acceptable trade-offs for a strong, simple proof of concept.
- rationale: The hackathon values a working, demonstrable loop over production-grade real-time transport. Simpler transport reduces integration risk and makes the frontend contract trivial to consume.
- impact: Progressive rendering must be emulated by the frontend applying complete message arrays; the backend never holds a streaming connection.
- follow_ups: Frontend must confirm it can apply full message arrays idempotently.

## [2026-09-12] decision — Provider abstraction with env-only failover
- agent: opencode / deepseek-flash
- requirements: REQ-NFR-01
- invariants: INV-012, INV-013
- files: `INVARIANTS.md`, `AGENTS.md`
- decision: All external capabilities sit behind narrow interfaces with configured fallback chains: LLM Gemini→DeepSeek; TTS ElevenLabs→edge-tts; STT Gemini→faster-whisper; web research Gemini grounding→deterministic price table. Selection is `.env`-only.
- rationale: Token/quota exhaustion on Gemini or ElevenLabs is probable during a 24-hour build. Env-only failover keeps development and the live demo alive without code changes.
- impact: A2UI output is validated independently of provider so the contract does not change when a provider is swapped. DeepSeek is text-only; STT and TTS fall back to local implementations.
- follow_ups: Implement `providers/registry.py` and a failover smoke test first.

## [2026-09-12] decision — Persisted generated UI with placeholder hydration and structural revalidation
- agent: opencode / deepseek-flash
- requirements: REQ-UI-01..04, REQ-BAG-08
- invariants: INV-021, INV-022
- files: `INVARIANTS.md`, `SPECS.md`
- decision: Generated UIs are persisted in SQLite per user and domain (`loans_credits` or `saving_bag`) using placeholders. The backend hydrates placeholders with fresh data immediately before delivery and runs an agent revalidation pass that may mutate structure.
- rationale: Placeholders prevent stale-data leakage; revalidation preserves the AGENTS.md requirement that the interface is a consequence of reasoning rather than a predetermined screen being refilled.
- impact: Requires a placeholder resolver, a versioned `generated_ui` table, and a revalidation hook. Data-only rehydration is explicitly insufficient.
- follow_ups: Define placeholder syntax and the revalidation trigger conditions.

## [2026-09-12] risk — Persisted UI could be mistaken for a predetermined screen
- agent: opencode / deepseek-flash
- requirements: REQ-LOOP-04, REQ-UI-03
- invariants: INV-017, INV-022
- files: `AGENTS.md`, `INVARIANTS.md`
- decision: Treat the revalidation pass as mandatory, not optional, and keep at least two structural mutation moments on stage.
- rationale: Hackathon rules forbid predetermined screens disguised as generated UI. Persistence without structural revalidation would violate the core thesis even if requirements are met.
- impact: The demo must visibly show structure (not just values) changing in response to context.
- follow_ups: Instrument the demo to highlight structural mutations.

## [2026-09-12] decision — LLM never computes financial math
- agent: opencode / deepseek-flash
- requirements: REQ-LM-03, REQ-LM-04, REQ-BAG-07
- invariants: INV-015
- files: `INVARIANTS.md`
- decision: A deterministic `engine/` module computes amortization, break detection, feasibility, and projections; the LLM only reasons about strategy and interface composition.
- rationale: Deterministic math guarantees correctness and reproducibility, makes the Kill Test meaningful, and demonstrates that MCP provides real capability rather than decorative tooling.
- impact: The engine becomes the most important unit-tested component and is insulated from provider outages.
- follow_ups: Author engine unit tests before wiring the agent to them.

## [2026-09-12] change — Local environment and secret isolation established
- agent: opencode / deepseek-flash
- requirements: none
- invariants: INV-040, INV-041, INV-012, INV-013
- files: `backend/.env`, `backend/.env.example`, `.gitignore`
- decision: Created `backend/.env` holding `GEMINI_API_KEY`, `DEEPSEEK_API_KEY`, and `ELEVENLABS_API_KEY` plus the provider-selection variables. Added `backend/.env.example` with names and placeholders only, and a root `.gitignore` that excludes `backend/.env`, `.env`, `.env.*`, and local data/artifacts.
- rationale: The build requires live provider credentials, and `INV-040` mandates they exist only in a git-ignored `.env`. Embedding provider selection in the same file keeps swaps env-only per `INV-013`.
- impact: The three keys were disclosed in a planning session and are therefore compromised per `INV-041`; they must be rotated after the event. No secret value appears in any tracked document. The backend still needs an entrypoint before the env is consumed.
- follow_ups: Implement `providers/registry.py` reading these variables; verify `.env` remains untracked once a git repository is initialized.

## [2026-09-12] decision — Storage split: local SQLite for development, Cloudflare D1 for showcase
- agent: opencode / deepseek-flash
- requirements: REQ-DATA-03, REQ-DATA-04, REQ-DATA-05, REQ-DATA-08
- invariants: INV-019, INV-020
- files: `INVARIANTS.md`, `SPECS.md`, `AGENTS.md`
- decision: Persistence is abstracted behind a repository port with two interchangeable adapters: `local_sqlite` (local SQLite file, used strictly in development) and `d1_http` (Cloudflare D1 reached via the Cloudflare REST API, used in the showcase). Selection is environment-only via `DB_BACKEND`. `CLOUDFLARE_D1_SQLITE` holds the D1 database UUID. The showcase backend is hosted locally behind a Cloudflare Tunnel. Wrangler is the migration tool for D1. On D1 unreachability or quota exhaustion the system falls back to the local seeded SQLite backend.
- rationale: D1 is managed SQLite, so the schema is portable, but the Python/FastAPI backend is not a Cloudflare Worker and can only reach D1 through the REST API. An abstraction keeps development strictly local (zero Cloudflare dependency) while the showcase runs on real D1, and a traced fallback protects the demo — "winning is mandatory".
- impact: Adds a required persistence port and adapters, D1-subset SQL constraints, new env keys, and a `wrangler.toml`. The database UUID alone is insufficient for runtime access: `CLOUDFLARE_ACCOUNT_ID` and a `D1 Read`/`D1 Write` API token are required before the showcase and will be added later. Development is not blocked.
- follow_ups: Implement the port and both adapters; create `wrangler.toml`; add `.wrangler/` to `.gitignore`.

## [2026-09-12] invariant-change — INV-020 modified; INV-019 added (Database backend abstraction)
- agent: opencode / deepseek-flash
- requirements: REQ-DATA-03, REQ-DATA-08
- invariants: INV-019 (new), INV-020 (modified), INV-022 (clarified)
- files: `INVARIANTS.md`
- decision: `INV-020` changed from "All data lives in **SQLite**. All data is mocked/seeded. No real banking integrations, no production database, no auth system." to "All data lives in **SQLite** through the repository abstraction (INV-019): a local SQLite file for development and **Cloudflare D1** for the showcase. All data is mocked/seeded. No real banking integrations, no general-purpose production database, no auth system." Added `INV-019` requiring a repository port, env-only backend selection, no Workers-binding assumption, a traced local fallback on D1 failure, and D1-subset schema/migrations/seed. Clarified `INV-022` to hydrate "from the configured database backend (INV-019)".
- rationale: The showcase requires a managed backend while development must remain fully local. Recording this as an invariant prevents silent divergence and keeps the failover guarantee non-negotiable.
- impact: Any future change to persistence must respect the port abstraction and env-only selection. Approval for this invariant change was explicitly granted by the human owner.
- follow_ups: none.

## [2026-09-12] change — Documentation and config updated for dual-backend persistence
- agent: opencode / deepseek-flash
- requirements: REQ-DATA-01, REQ-DATA-06, REQ-DATA-07, REQ-NFR-06, REQ-NFR-07
- invariants: INV-019, INV-020
- files: `SPECS.md`, `AGENTS.md`, `backend/.env`, `backend/.env.example`, `wrangler.toml`, `.gitignore`
- decision: Added `REQ-DATA-03..08` and `REQ-NFR-06/07`; updated `REQ-DATA-01`. Updated `AGENTS.md` stack, repository layout, the MCP-only rule, the documentation-fetch table (Cloudflare D1 + Wrangler), the secrets list, and the testing section (parity + fallback tests). Added `DB_BACKEND`, `CLOUDFLARE_D1_SQLITE`, `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN`, and `D1_FALLBACK_LOCAL` to the environment. Added `wrangler.toml` for D1 migrations and `.wrangler/` to `.gitignore`. Clarified that using D1 as a managed SQLite showcase host does not violate the "no production databases" hackathon constraint.
- rationale: Implementation must follow documented requirements and invariants; the environment and Wrangler config make the backend swap and D1 migrations reproducible.
- impact: `CLOUDFLARE_ACCOUNT_ID` and `CLOUDFLARE_API_TOKEN` are intentionally left blank until before the showcase. The local development path requires no Cloudflare credentials.
- follow_ups: Populate the two Cloudflare credentials before the D1 parity run.

## [2026-09-12] risk — D1 network dependency and platform limits during the showcase
- agent: opencode / deepseek-flash
- requirements: REQ-DATA-08, REQ-NFR-07, REQ-DEMO-04
- invariants: INV-019, INV-005
- files: `INVARIANTS.md`, `SPECS.md`, `AGENTS.md`
- decision: Treat D1 as an external, fallible dependency with an approved local fallback, and constrain all SQL to the D1-compatible subset.
- rationale: Documented D1 limits are material for the demo: 100 bound parameters and 100 KB per statement, 2 MB rows, 500 MB per free database, a single-threaded database, and a 30-second query ceiling. Access is via the REST API over the Cloudflare Tunnel, so venue connectivity and latency affect every query. A full venue-internet outage would also drop the tunnel, which the local fallback cannot cover.
- impact: Writes must be batched, reads minimized, and the recorded golden-path video (`REQ-DEMO-04`) remains mandatory insurance for a total outage.
- follow_ups: Measure D1 round-trip latency during the first remote parity run and adjust batching.

## [2026-09-12] invariant-change — D1 dropped; persistence is local SQLite only (INV-019/020/022)
- agent: opencode / deepseek-flash
- requirements: REQ-DATA-03, REQ-DATA-04, REQ-DATA-05, REQ-NFR-06
- invariants: INV-019 (modified), INV-020 (modified), INV-022 (modified)
- files: `INVARIANTS.md`
- decision: `INV-019` changed from a multi-adapter database abstraction with D1 and fallback to: "Persistence is a single **local SQLite** database reached only through the persistence port; there is no remote or managed database. The database file lives on the same host as the backend. Internet exposure is provided exclusively by a Cloudflare Tunnel in front of the local backend; no application data or processing leaves the host." `INV-020` changed to "All data lives in a local SQLite file accessed through the persistence port (INV-019). All data is mocked/seeded. No real banking integrations, no remote or managed database, no auth system." `INV-022` changed from hydrating "from the configured database backend" to "from the local database".
- rationale: The team reversed the Cloudflare D1 decision. Everything runs locally and the backend is merely exposed through a Cloudflare Tunnel; there is no second backend, so the adapter/fallback machinery and its subset constraints no longer apply. Approval for this invariant change was explicitly granted by the human owner ("Full wipe").
- impact: All D1, Wrangler, and failover concepts are removed from the architecture. Internet exposure is a tunnel concern, not a persistence concern. The provider failover rules (INV-012/013) for LLM/TTS/STT are unaffected.
- follow_ups: None.

## [2026-09-12] change — Full wipe of the D1 backend and rebuild as local-only
- agent: opencode / deepseek-flash
- requirements: REQ-DATA-01, REQ-DATA-02, REQ-DATA-03, REQ-DATA-04, REQ-DATA-05, REQ-NFR-06
- invariants: INV-019, INV-020
- files: deleted `backend/db/` (old), `backend/tests/` (old), `backend/wrangler.toml`, `backend/db.py`, `backend/db/migrations/`, `backend/db/emit_seed_sql.py`, `backend/data/`; created `backend/config.py`, `backend/db/{__init__,port,local_sqlite,schema,sql_utils,seed,init}.py`, `backend/db/schema.sql`, `backend/tests/{test_local_sqlite,test_schema,test_seed}.py`; updated `backend/.env`, `backend/.env.example`, `.gitignore`, `SPECS.md`, `AGENTS.md`
- decision: Executed a full wipe of the previous persistence implementation and rebuilt it as a flat, local-only layer: `DatabasePort` + `LocalSQLiteDatabase`, `schema.sql` as the single schema source, a deterministic `seed.py`, and a `python -m db.init` CLI. Removed the `db/backends/` split, `d1_http`, `FallbackDatabase`, the migration mirror, the seed-SQL emitter, and the stray name-colliding `backend/db.py`. Removed `DB_BACKEND`, `D1_FALLBACK_LOCAL`, and all `CLOUDFLARE_*` variables. Added a local run + Cloudflare Tunnel runbook to `AGENTS.md §11`.
- rationale: The prior design carried D1-specific structure that could never run locally. A clean local-only rebuild is simpler to build, repair, and trace, matching the team's preference for a strong local proof of concept exposed via a tunnel.
- impact: Backend tests reduced to 6 and all pass; `python -m db.init` creates and seeds all 18 tables (2 users, 96 transactions). `httpx` remains in `requirements.txt` for the future LLM/TTS/STT providers but is not used by persistence.
- follow_ups: Implement the FastAPI app and MCP servers on top of the persistence port; exercise the tunnel once the app listens on `127.0.0.1:8000`.

## [2026-09-12] change — A2UI catalog contract frozen (`A2UI_CATALOG.md`)
- agent: opencode / deepseek-flash
- requirements: REQ-LOOP-06
- invariants: INV-016, INV-023
- files: `A2UI_CATALOG.md` (new), `SPECS.md`, `AGENTS.md`
- decision: Added the frozen backend/frontend interface contract: catalog IDs (`amitie.standard.v1`, `amitie.voz-color.v1`), A2UI v0.9.1 message model, JSON-Pointer data binding, the full primitive and domain component vocabulary with props, the action-name set, the `{{...}}` placeholder/revalidation convention, and a required M3 subset. Added `REQ-LOOP-06` requiring generated interfaces to use only components/actions defined in the contract, and referenced the document from `AGENTS.md` §4 as a root document.
- rationale: The backend generates A2UI JSON by component name; the frontend implements those names. Without a frozen contract the two teams drift. Defining it now unblocks M3 and the frontend in parallel.
- impact: Component renames/removals are now breaking changes requiring a new catalog ID and a changelog entry. The frontend must confirm support for the M3 subset before M4+ components are emitted.
- follow_ups: Have the frontend team confirm the M3 subset; verify exact field shapes against the A2UI agent SDK when the agent is implemented.

## [2026-09-12] change — M1 engines and observability implemented
- agent: opencode / deepseek-flash
- requirements: REQ-LM-03, REQ-LM-04, REQ-BAG-07, REQ-NFR-02, REQ-NFR-03
- invariants: INV-015, INV-018
- files: `backend/engine/{__init__,amortization,break_detection,feasibility}.py`, `backend/observability/{__init__,context,tracing,logging,middleware}.py`, `backend/tests/test_engine.py`, `backend/tests/test_observability.py`
- decision: Implemented the deterministic engines (`simulate`, `detect_plan_breaks`, `project_completion`, `compute_feasibility`, `available_monthly_capacity`) as pure functions with no IO, and the observability layer (trace context via contextvars, `Tracer` persisting to the `traces` table, JSON logging, and a framework-agnostic ASGI `TraceMiddleware` that assigns `x-trace-id` and records each request). Added 13 new tests.
- rationale: M1 has no external dependencies, so it de-risks the critical path and locks the deterministic math the LLM must never perform (INV-015) plus the traceability the demo needs (INV-018). The ASGI middleware avoids a FastAPI dependency until M3.
- impact: Full backend suite is now 19 tests, all passing. `simulate` supports `snowball`/`avalanche`/`minimum` strategies, per-month `events`, and returns per-month snapshots; break detection finds the first negative-cash month. No new runtime dependencies were added.
- follow_ups: M2 providers (Gemini + failover wiring), then M3 in-process MCP finance tools + FastAPI + agent to run the La Mesa debt-intent slice.

## [2026-09-12] change — M2 provider layer implemented with Gemini → DeepSeek failover
- agent: opencode / deepseek-flash
- requirements: REQ-NFR-01, REQ-LM-03
- invariants: INV-012, INV-013, INV-018
- files: `backend/providers/{__init__,base,gemini,deepseek,registry,gateway}.py`, `backend/tests/test_providers.py`, `backend/config.py`, `backend/.env`, `backend/.env.example`, `backend/requirements.txt`, `backend/README.md`
- decision: Added normalized provider interfaces (`ChatMessage`, `ToolSpec`, `ToolCall`, `Usage`, `LLMResult`, and a `ProviderError` → `ProviderUnavailableError`/`ProviderResponseError` taxonomy). Implemented `GeminiLLM` on `google-genai` (primary; maps function calls, JSON schema, usage, and `genai.errors.APIError.code`), `DeepSeekLLM` on raw `httpx` against the OpenAI-compatible `/chat/completions` endpoint (fallback; tool calls, JSON output, usage; thinking disabled by default), an env-only `registry.build_llm`, and `FallbackLLM` with per-call failover, a 30s cooldown circuit breaker, and one trace event per attempt. Extended `Settings` with provider configuration (all fields now defaulted). Set `DEEPSEEK_MODEL=deepseek-flash` per current DeepSeek docs and added `LLM_FAILOVER_COOLDOWN_SECONDS` and `DEEPSEEK_THINKING`. Added `google-genai` to requirements.
- rationale: `REQ-NFR-01` requires development and the demo to survive Gemini quota/rate-limit exhaustion. A provider-agnostic interface plus an env-only failover chain keeps the swap to a config change and keeps the agent working. DeepSeek docs verified before implementation (AGENTS.md §7): OpenAI-compatible base `https://api.deepseek.com`, function calling, JSON output, and the current model name `deepseek-flash`.
- impact: Full backend suite is now 29 tests, all passing (Gemini adapter construction verified against installed `google-genai` 2.23.0; no network calls in tests via `httpx.MockTransport` and fakes). Failover is non-sticky and traced, unlike the removed DB fallback. TTS/STT provider interfaces were deliberately deferred to M7.
- follow_ups: M3 — in-process `finance` MCP tools + FastAPI + Gemini agent + hydration → first end-to-end La Mesa debt-intent slice. Consider a live provider smoke test gated by `RUN_PROVIDER_SMOKE=1`.

## [2026-09-12] change — DeepSeek adapter and tests migrated from httpx to httpx2
- agent: opencode / deepseek-flash
- requirements: REQ-NFR-01
- invariants: INV-012, INV-013
- files: `backend/providers/deepseek.py`, `backend/tests/test_providers.py`, `backend/requirements.txt`, `backend/README.md`
- decision: Replaced `httpx` with `httpx2` in the DeepSeek fallback adapter and its tests, and swapped the direct requirement `httpx>=0.27` for `httpx2>=2.12`.
- rationale: MCP Python SDK v2 is built on `httpx2`, so aligning our direct HTTP dependency with it avoids mixing two HTTP clients in our own code. Verified against the primary docs (AGENTS.md §7) that every symbol we use exists in httpx2: `AsyncClient`, `post`, `aclose`, `MockTransport`, `Response`, `Request`, and the `HTTPError` hierarchy. The migration was mechanical (`httpx.` → `httpx2.`).
- impact: All 29 tests pass unchanged on httpx2 2.12.0, and no direct `httpx` references remain in our code. Note this does not remove `httpx` from the environment: `google-genai` and Starlette's `TestClient` still depend on it. There is no module-level conflict; the two packages coexist.
- follow_ups: M3.0 spike — ADK custom `BaseLlm` adapter, in-memory `mcp.Client(MCPServer(...))`, and the MCP tool integration choice.

## [2026-09-12] change — M3.0 de-risk spike passed; M3 interfaces confirmed
- agent: opencode / deepseek-flash
- requirements: REQ-LOOP-01, REQ-LOOP-02, REQ-LOOP-03, REQ-LOOP-05
- invariants: INV-011, INV-012, INV-014
- files: `backend/requirements.txt` (throwaway spike kept out of the repo at `/tmp/opencode/spike_m3.py`)
- decision: Verified the three riskiest M3 interfaces with a runnable spike before building. (1) In-memory MCP works with `mcp` 2.2.0 via `async with Client(MCPServer("spike")) as client:` — `list_tools()` and `call_tool()` succeed with no transport. (2) A custom ADK `BaseLlm` subclass (`GatewayLlm`) can delegate to our `providers` gateway: subclass `google.adk.models.base_llm.BaseLlm` (only field is `model`; add a `provider: Any` field with `arbitrary_types_allowed=True`), implement `async generate_content_async(self, llm_request, stream=False)` as an async generator yielding `LlmResponse`, and map `LlmRequest.contents`/`config.system_instruction` → `ChatMessage` and `LLMResult` → `LlmResponse` (function-call parts via `types.Part.from_function_call`, text via `types.Part.from_text`). (3) ADK's tool loop works through the custom model: the provider emitted a tool call, ADK executed the tool, called the model again, and produced the final answer (`ADK provider calls: 2`). ADK `MCPToolset` is transport-only (stdio/SSE/streamable-HTTP) with no in-memory option, so MCP tools will be exposed to ADK by wrapping our `Toolbox` as ADK function tools.
- rationale: The custom-model + in-process-MCP combination is the highest-risk part of M3. Proving it before writing the slice avoids discovering an integration wall mid-build, matching the "build, repair, trace fast" priority.
- impact: Pinned and installed: `google-adk` 2.9.0, `mcp` 2.2.0, `a2ui-agent-sdk` 0.6.0, `fastapi` 0.141.1, `uvicorn` 0.52.4, added to `requirements.txt`. The `a2ui-agent-sdk` 0.6.0 layout is restructured (submodules include `adk`, `schema`, `parser`, `basic_catalog`, `template`), so its exact API will be confirmed in M3.1. ADK logs "Skipping missing token usage metadata" because the spike did not populate `LlmResponse.usage_metadata`; M3.3 should populate it from `LLMResult.usage`.
- follow_ups: M3.1 — machine-readable A2UI catalog for the M3 subset + system prompt + validator.

## [2026-09-12] change — M3.1 machine-readable A2UI catalog, prompt, and validator
- agent: opencode / deepseek-flash
- requirements: REQ-LOOP-06, REQ-LOOP-02
- invariants: INV-016, INV-011 (see risk below)
- files: `backend/ui_contract/{__init__,catalog,prompt,validator}.py`, `backend/ui_contract/catalog.json`, `backend/tests/test_a2ui_catalog.py`
- decision: Added the M3 interface implementation. `catalog.json` is the machine source (catalogId `amitie.standard.v1`, v0.9 message types, the 12-component M3 subset with required props and action names). `catalog.py` loads it; `prompt.py` generates the A2UI system prompt from it (message types, binding rule, component table, allowed actions, and the `persist_ui` terminal-tool output contract); `validator.py` defines `UiValidator`, a strict catalog-driven `CatalogValidator` (message envelopes, unknown components, required props, prop types, unknown actions, dangling child references, unknown catalogId), and an `SdkValidator` adapter. Named the package `ui_contract` because `a2ui` would shadow the installed `a2ui-agent-sdk` package.
- rationale: The agent must be constrained to exactly the components the frontend implements, and payloads must be rejected before delivery. A catalog-driven validator is deterministic, fast, and testable, satisfying the closed-loop reliability priority.
- impact: Full suite is now 42 tests, all passing (13 new). Component-name parity with `A2UI_CATALOG.md` §8 is asserted by test.
- risk: `INV-011` requires A2UI payloads to be validated with the A2UI agent SDK, but `a2ui-agent-sdk` 0.6.0's `A2uiValidator.validate` raises an internal error (`cannot use 'dict' as a dict key`) even on a valid payload against the bundled basic catalog, so `SdkValidator` is exposed and safe but not active. `CatalogValidator` is authoritative until the SDK validator is fixed or the custom catalog is authored in the SDK's JSON-Schema format. This invariant tension is flagged for an explicit decision.
- follow_ups: Decide the SDK-validation path (fix/wrap the SDK validator, author the catalog in the SDK format, or amend `INV-011`). Then M3.2 — `finance`/`ui` MCP tools + `hydration/`.

## [2026-09-12] change — M3.2 finance/ui MCP tools, toolbox, and hydration
- agent: opencode / deepseek-flash
- requirements: REQ-LM-01, REQ-UI-01, REQ-UI-02, REQ-UI-04
- invariants: INV-014, INV-019, INV-021, INV-022
- files: `backend/mcp_servers/{__init__,toolbox}.py`, `backend/mcp_servers/finance/{__init__,service,server}.py`, `backend/mcp_servers/ui/{__init__,service,server}.py`, `backend/hydration/{__init__,placeholders,service}.py`, `backend/tests/{test_toolbox,test_finance_tools,test_ui_tools,test_hydration}.py`, `AGENTS.md`, `backend/README.md`
- decision: Implemented in-process MCP servers and the toolbox seam. Finance server: `get_profile`, `get_liabilities`, `get_income_streams`, `get_subscriptions`, `get_cash_flow(months)`, and the aggregate `get_financial_context` whose shape is the binding contract. UI server: `persist_ui` (validates via `CatalogValidator`, returns `{status:"error", issues}` for retry, else stores `generated_ui` and returns the A2UI messages), `hydrate_ui` (re-runs `financial_context` for freshness, resolves `{{...}}`, runs the no-op revalidation hook, returns components + fresh data model), and `a2ui_action` (logs to `ui_actions`). `InProcessToolbox` opens one in-memory `mcp.Client` per server via `AsyncExitStack`, maps `mcp.types.Tool` -> `ToolSpec`, and normalizes results (unwrap `structured_content["result"]`, else parse `TextContent` JSON). `user_id` is an explicit tool parameter per the locked decision.
- rationale: MCP must be the only door to data and actions (INV-014), so the agent will talk to these servers through the toolbox. Re-running `financial_context` at hydration time makes `GET /ui/{id}` always current (REQ-UI-02) without a generic data-store coupling. Verified the two MCP mechanics first: async tools dispatch over the in-memory client, and dict returns arrive as JSON `TextContent`.
- impact: Full suite now 52 tests, all passing (10 new). Named the package `mcp_servers` (not `mcp`) because `backend/mcp/` would shadow the installed `mcp` SDK — the same collision class as `a2ui`. `persist_ui` includes the A2UI messages in its response so the orchestrator does not need a second round trip.
- follow_ups: M3.3 — ADK `GatewayLlm(BaseLlm)` adapter over our provider gateway, an `LlmAgent` with these tools, and the turn service. Revisit SDK validation before the M3.5 acceptance test.

## [2026-09-12] change — M3.3 ADK agent over the provider gateway
- agent: opencode / deepseek-flash
- requirements: REQ-LOOP-01, REQ-LOOP-02, REQ-LOOP-03, REQ-LM-01
- invariants: INV-011, INV-012, INV-014, INV-018
- files: `backend/agent/{__init__,model,tools,service}.py`, `backend/tests/{test_agent_model,test_agent_tools,test_agent_service}.py`, `backend/config.py`, `backend/.env`, `backend/.env.example`, `AGENTS.md`, `backend/README.md`
- decision: Implemented ADK orchestration backed by the M2 gateway. `agent/model.py` provides `GatewayLlm(BaseLlm)` which maps `LlmRequest.contents`/`config.system_instruction` -> `ChatMessage`s, `config.tools[].function_declarations` -> `ToolSpec`s, calls the gateway, and maps `LLMResult` -> `LlmResponse` (`function_call`/text parts, `usage_metadata`, `turn_complete = not tool_calls`), with a per-turn model-call guard (`reset_calls`, default 6). `agent/tools.py` wraps each MCP tool as an `McpTool(BaseTool)` (`_get_declaration()` from the `ToolSpec`, `run_async` delegating to the MCP `Toolbox`). `agent/service.py` builds the `LlmAgent` (instruction from `ui_contract.build_system_prompt`), keeps one `InMemoryRunner` with persistent ADK sessions keyed by our `session_id` (`get_session`/`create_session(session_id=...)`), runs a turn with `RunConfig(max_llm_calls=6)`, captures the terminal `persist_ui` result, and returns `{status, surface_id, a2ui, assistant_text}`. Errors (provider failure, call limit, missing `persist_ui`) return `{status:"error", ...}` and emit an `agent` trace.
- rationale: ADK remains the orchestrator (INV-011) while Gemini -> DeepSeek failover stays in the gateway (INV-012) and MCP remains the only door to data/actions (INV-014). Verified the ADK integration surface before coding: `BaseTool` is a plain ABC (subclass-friendly), tool schemas arrive via `parameters_json_schema`, and `InMemorySessionService.create_session` accepts a custom `session_id`.
- impact: Full suite now 60 tests, all passing (8 new). The turn service is network-free in tests via a scripted provider. `assistant_text` is returned alongside `a2ui`. Added `AGENT_MAX_MODEL_CALLS=6` to the environment.
- follow_ups: Revisit the `INV-011` SDK-validation decision, then M3.4 — FastAPI routers + dependency injection, then the M3.5 acceptance test.

## [2026-09-12] change — M3.4 FastAPI HTTP API + dependency injection
- agent: opencode / deepseek-flash
- requirements: REQ-API-01..08, REQ-LOOP-05
- invariants: INV-010, INV-017, INV-018, INV-023
- files: `backend/api/{__init__,app,main,dependencies,schemas}.py`, `backend/api/routers/{__init__,session,message,action,ui,debug}.py`, `backend/tests/test_api.py`, `AGENTS.md`, `backend/README.md`
- decision: Implemented the REST API over the agent stack. `create_app(provider=..., settings=...)` creates the DB and tracer eagerly (so `TraceMiddleware` can be mounted) and builds the MCP toolbox + `AgentService` in the lifespan. Endpoints: `POST /api/session` (creates a `sessions` row), `POST /api/message` (validates the session, runs a turn, updates `active_surface_id`), `POST /api/action` (derives `user_id` from `generated_ui`, records the interaction through the MCP `a2ui_action` tool, then runs a turn using the user's most recent session for continuity), `GET /api/ui/{surface_id}` (MCP `hydrate_ui`), `GET /debug/trace/{trace_id}`, and `GET /healthz`. CORS is permissive (`allow_origins=["*"]`). Errors return HTTP 200 with `{status:"error", ...}`; unknown session/surface return 404.
- rationale: The frontend needs the frozen REST contract over HTTP (INV-010, INV-023). Keeping `a2ui_action` and `hydrate_ui` behind MCP preserves INV-014/INV-017. Building the app via a factory with an injectable provider makes the full loop testable without any network.
- impact: Full suite now 62 tests, all passing (2 new, including the end-to-end HTTP loop via `TestClient`). `uvicorn api.main:app` now runs the service. Startup applies the schema only (seeding remains `python -m db.init`). This completes the M3 vertical slice at the HTTP level; only the M3.5 acceptance test and the `INV-011` decision remain.
- follow_ups: Resolve the `INV-011` SDK-validation decision, then run the M3.5 acceptance test.

## [2026-09-12] change — A2UI SDK-format catalog + jsonschema validation; flat v0.9 component format
- agent: opencode / deepseek-flash
- requirements: REQ-LOOP-06
- invariants: INV-011, INV-016
- files: `backend/ui_contract/catalog.schema.json`, `backend/ui_contract/schema_registry.py`, `backend/ui_contract/schemas/0.9/{common_types,server_to_client}.json`, `backend/ui_contract/validator.py`, `backend/ui_contract/prompt.py`, `backend/mcp_servers/ui/service.py`, `backend/tests/test_a2ui_schema_validation.py`, test payloads, `A2UI_CATALOG.md`, `AGENTS.md`, `backend/README.md`, `requirements.txt`
- decision: Resolved `INV-011` by authoring our catalog in the A2UI SDK's JSON-Schema format (`catalog.schema.json`, catalogId `amitie.standard.v1`) and validating payloads with `jsonschema` against the A2UI v0.9 schemas. Vendored `common_types.json` and `server_to_client.json` into `ui_contract/schemas/0.9/`, and built a `referencing.Registry` that also maps `https://a2ui.org/specification/v0_9/catalog.json` to our catalog so the cross-document `$ref`s resolve. `JsonschemaValidator` is now the structural validator; `CatalogValidator` remains a semantic pass (known `catalogId`, known action names) that JSON Schema cannot express; `validate_messages` runs schema then semantics; `SdkValidator` now delegates to `JsonschemaValidator`.
- **breaking correction:** the A2UI SDK schemas and the official v0.9 docs confirmed that v0.9 uses the **flat** component format — `{"id": "...", "component": "Text", "text": "..."}` with props as siblings — not the v0.8 nested form `{"component": {"Text": {...}}}` that `A2UI_CATALOG.md` and our validator originally used. All payloads, the validator, the prompt, and the contract doc were corrected to flat. `catalogId` stays `amitie.standard.v1` because the nested form was never delivered to or consumed by the frontend; the frontend must implement the flat shape.
- rationale: This is the approach the human owner selected over amending `INV-011`. It also produced immediate value: the SDK schema validation caught the flat-vs-nested bug that our hand-written validator had missed, proving the validation is meaningful rather than decorative.
- impact: Full suite now 70 tests, all passing (8 new, including unknown-component/missing-prop/bad-version rejection, relative `$ref` resolution, and a test proving jsonschema alone cannot catch unknown action names while the semantic pass does). Added explicit `jsonschema` and `referencing` requirements.
- follow_ups: Run the M3.5 acceptance test; notify the frontend team of the flat v0.9 component shape.

## [2026-09-12] change — M3.5 acceptance test: debt-intent slice passes end to end
- agent: opencode / deepseek-flash
- requirements: REQ-LOOP-01..05, REQ-LM-01, REQ-LM-02
- invariants: INV-010, INV-011, INV-014, INV-017
- files: `backend/tests/test_m3_acceptance.py`, `backend/README.md`
- decision: Added the explicit M3 acceptance test. Over `TestClient` with a scripted provider (no network): a debt sentence -> the agent reads `get_financial_context` through MCP -> emits a `DebtNode` + `TradeoffScale` surface (validated by `validate_messages`, i.e. A2UI SDK schemas + semantic pass) -> `GET /api/ui/{id}` hydrates fresh data (`totals.debt = 127200`) -> a `tune_tradeoff` action regenerates the interface -> the turn is traced.
- rationale: This is the M3 definition of done (the closed interaction loop over HTTP), and it is the exact behavior the AGENTS.md thesis requires rather than a static screen.
- impact: Full suite now 71 tests, all passing. M3 is complete end to end; the `INV-011` SDK-validation decision is resolved.
- follow_ups: M4 — `simulate_plan` + `detect_plan_breaks` MCP tools, the unprompted `BreakAlert` mutation, and real structural revalidation (replacing the no-op hook). Notify the frontend team of the flat v0.9 shape.

## [2026-09-12] change — M4 La Mesa mutations: simulate_plan, proactive BreakAlert, repair, and deterministic revalidation
- agent: opencode / deepseek-flash
- requirements: REQ-LM-03, REQ-LM-04, REQ-LM-05, REQ-LM-06, REQ-UI-03, REQ-UI-04
- invariants: INV-015, INV-022, INV-017
- files: `backend/engine/planning.py`, `backend/mcp_servers/finance/{service,server}.py`, `backend/hydration/service.py`, `backend/mcp_servers/ui/{service,server}.py`, `backend/ui_contract/{catalog.json,catalog.schema.json}`, `backend/agent/service.py`, `backend/tests/{test_planning,test_finance_plan_tools,test_revalidation,test_m4_acceptance}.py`, `A2UI_CATALOG.md`, `SPECS.md`, `AGENTS.md`, `backend/README.md`
- decision: Added the pure `engine/planning.py` adapter (`liabilities_from_context`, `monthly_cashflow`, `run_simulation`, `plan_payload`, `break_payload`, `build_plan`). The finance MCP server now exposes `simulate_plan` and `detect_plan_breaks` (the engine computes; the LLM only chooses strategy/parameters, INV-015). The catalog gained `BreakAlert` and `PlanTable` (additive; catalog ID unchanged per A2UI_CATALOG §10). `persist_ui` accepts a `simulation` descriptor stored in `bindings_json`. `hydration/service.revalidate` is no longer a no-op: given a simulation it recomputes the plan from fresh data, writes `context["plan"]`, and idempotently inserts/updates a canonical `plan-section` containing `PlanTable` and (iff broken) `BreakAlert`; `hydrate_ui` persists the mutated structure and bumps `version` only on actual change. The agent instruction now mandates simulate → detect → proactive `BreakAlert` → repair → reflow.
- rationale: This delivers the two signature mutation moments (unprompted `BreakAlert`; repair/reflow) and makes `GET /api/ui` genuinely structural (INV-022) rather than a data re-fill. Deterministic revalidation keeps it fast and testable while respecting INV-015. Adding `PlanTable.months` as an array-or-binding was required because A2UI has no `DynamicArray`; the binding keeps persisted templates data-free.
- impact: Full suite now 78 tests, all passing (7 new). The seeded persona deterministically breaks at **month 1** (income 19000 − expenses 15367.09 − minimums 7850 = −4217.09); a repair with `extra_income=8000` clears it. The `events` parameter is supported so a later break can be scripted for the live demo. `REQ-LM-03..06` and `REQ-UI-03..04` are marked satisfied in SPECS.
- follow_ups: M5 — El Revés negotiation. Frontend must implement `BreakAlert` and `PlanTable` (flat v0.9 shape).

## [2026-09-12] change — M5 El Revés: two-persona negotiation, take-control, simulated acceptance
- agent: opencode / deepseek-flash
- requirements: REQ-LM-07, REQ-LM-08, REQ-LM-09, REQ-API-06
- invariants: INV-014, INV-015, INV-017
- files: `backend/engine/offer.py`, `backend/engine/planning.py`, `backend/mcp_servers/finance/{service,server}.py`, `backend/mcp_servers/ui/{service,server}.py`, `backend/agent/negotiation.py`, `backend/api/{app,dependencies,schemas}.py`, `backend/api/routers/{negotiation,action}.py`, `backend/ui_contract/{catalog.json,catalog.schema.json}`, `backend/tests/{test_offer_engine,test_offer_tools,test_negotiation_service,test_m5_acceptance}.py`, `A2UI_CATALOG.md`, `SPECS.md`, `AGENTS.md`, `backend/README.md`
- decision: Implemented El Revés. `engine/offer.py` deterministically builds offers from `lender_policies` (consolidation/settlement within `aprFloor`/`maxMonths`/`minSettlementPct`) and evaluates feasibility by modeling the offer as a single liability and running the same simulation (`planning.run_simulation` gained an `offer` override). The **finance** MCP server gained `get_lender_policies`, `generate_offer`, `evaluate_offer`, `accept_offer` (tool placement per the decision, honoring INV-014). The **ui** MCP server gained `record_negotiation_round`, `get_negotiation`, `get_session`, `set_session_context`. `agent/negotiation.py` provides `NegotiationService`: one ADK agent with the instruction swapped per persona (`bank`/`advocate`), alternating rounds, recording each via MCP and emitting `OfferCard` + `NegotiationTranscript` via `persist_ui`; `take_control` records the user's position, sets state, disables the advocate, and the bank responds. API: `POST /api/negotiation/{session}/turn`, `.../take-control`, and `accept_offer` routed through `POST /api/action` (simulated acceptance → final confirmed plan with next steps). Catalog gained `OfferCard` and `NegotiationTranscript` (additive; ID unchanged). Negotiation state lives in `sessions.context_json`.
- rationale: El Revés is the negotiation beat of the La Mesa thesis; the LLM drives persona reasoning while the engine computes all numbers (INV-015) and MCP remains the only door to data/actions (INV-014). Simulated acceptance keeps the demo self-contained.
- impact: Full suite now 85 tests, all passing (7 new). `REQ-LM-07..09` and `REQ-API-06` are marked satisfied. The acceptance test runs bank → advocate → take-control → accept over HTTP and asserts a final feasible plan with no `BreakAlert` and four persisted rounds.
- follow_ups: M6 — Saving Bags. Frontend must implement `OfferCard` and `NegotiationTranscript` (flat v0.9 shape).

## [2026-09-12] change — M6 Saving Bags: research, dated funding plan, loan handoff
- agent: opencode / deepseek-flash
- requirements: REQ-BAG-01..08, REQ-API-05
- invariants: INV-002, INV-012, INV-013, INV-014, INV-015, INV-021, INV-022
- files: `backend/engine/savings.py`, `backend/providers/research.py`, `backend/providers/registry.py`, `backend/providers/__init__.py`, `backend/config.py`, `backend/mcp_servers/savings/{__init__,service,server}.py`, `backend/hydration/service.py`, `backend/mcp_servers/ui/service.py`, `backend/agent/service.py`, `backend/api/{app,schemas}.py`, `backend/api/routers/saving_bags.py`, `backend/ui_contract/{catalog.json,catalog.schema.json}`, `backend/db/seed.py`, `backend/tests/{test_savings_engine,test_research_provider,test_savings_tools,test_hydration_savings,test_m6_acceptance}.py`, `backend/tests/{test_a2ui_catalog,test_a2ui_schema_validation}.py`, `A2UI_CATALOG.md`, `SPECS.md`, `AGENTS.md`, `backend/README.md`, `backend/.env.example`
- decision: Implemented Saving Bags. `engine/savings.py` deterministically turns a research snapshot + inferred answers into a cost estimate and a dated funding plan (reusing `engine/feasibility.py`); the LLM never computes numbers (INV-015). New research provider chain (`ResearchProvider`): `GeminiGroundingResearch` (Google Search) → `StaticPriceTableResearch`, env-selected and wrapped by `FallbackResearch`; `build_research` degrades to the fallback when no Gemini key is configured. New `savings` MCP server (`create_bag`, `get_bag`, `list_bags`, `answer_bag`, `research_costs`, `estimate_total`, `compute_feasibility`, `refresh_bag`, `get_savings_snapshot`); research snapshots are append-only in `saving_bag_research` and the plan upserts a single row in `saving_bag_plan` (REQ-BAG-04). `AgentService` is generalized to route both pillars from `/api/message`. Hydration is now domain-aware: the `saving_bag` descriptor path loads the bag snapshot into `/savings` and appends a canonical `savings-section` (`GoalJar` + `ProgressBar` + `CashFlowTimeline`, plus a warning/danger `Card` when off-track), bumping `generated_ui.version` on structural change (REQ-BAG-08, INV-022). New endpoints per REQ-API-05; every mutation resolves deterministic writes through MCP then runs an agent turn and returns a full A2UI array (REQ-LOOP-05). Catalog gained `List`, `ProgressBar`, `TextField`, `CashFlowTimeline`, `GoalJar` and actions `refresh_bag`, `adjust_goal` (additive; catalog ID unchanged).
- rationale: Saving Bags is the second pillar (INV-002) and the "vague goal → researched, dated, funded plan" beat. Keeping all arithmetic in the engine and all reads/writes behind MCP preserves INV-014/INV-015; the loan handoff reuses the M5 `OfferCard` + `accept_offer` path into La Mesa, so the two pillars connect.
- impact: Full suite now 107 tests, all passing (22 new). `REQ-BAG-01..08` and `REQ-API-05` are marked satisfied. The drift in `test_a2ui_catalog`/`test_a2ui_schema_validation` was removed: the schema component set is now asserted against `catalog.json`, the single source of truth. Also fixed the seeded `g_ana_plan` surface, which still used the obsolete v0.8 nested component shape and `catalog_id="standard"`.
- follow_ups: Frontend must implement `GoalJar`, `CashFlowTimeline`, `ProgressBar`, `TextField`, `List` and actions `refresh_bag`/`adjust_goal`. M7 — Voz y Color.

## [2026-09-12] change — M7 Voz y Color: automatic accessible catalog, speech, audio in/out
- agent: opencode / deepseek-flash
- requirements: REQ-ACC-01..06, REQ-API-07, REQ-NFR-01
- invariants: INV-003, INV-012, INV-013, INV-014, INV-016, INV-017, INV-021, INV-022
- files: `backend/ui_contract/{voz_color.json,catalog.py,validator.py,prompt.py}`, `backend/providers/{voice.py,registry.py,__init__.py}`, `backend/config.py`, `backend/mcp_servers/voice/{__init__,service,server}.py`, `backend/mcp_servers/ui/{service,server}.py`, `backend/hydration/speech.py`, `backend/agent/{speech,service,negotiation}.py`, `backend/api/{app,schemas}.py`, `backend/api/routers/{message,audio}.py`, `backend/audio_cache/.gitkeep`, `backend/tests/{test_voice_providers,test_voice_tools,test_catalog_voz_color,test_accessibility,test_m7_acceptance}.py`, `A2UI_CATALOG.md`, `SPECS.md`, `AGENTS.md`, `backend/README.md`, `backend/.env.example`, `backend/requirements.txt`
- decision: Implemented Voz y Color. The accessible catalog `amitie.voz-color.v1` is a real catalog (`voz_color.json`) that declares `extends: amitie.standard.v1`, so it reuses the standard component set; `catalog.py` loads a registry and `CatalogValidator` now resolves each surface's catalog from its `createSurface` (JS validation stays on the shared schema). Accessibility is automatic (INV-003): `persist_ui` reads `accessibility_profiles` and **pins** the catalog (voz-color when flagged, standard otherwise) and derives a speech text from the surface when none is supplied. New voice provider chains (`providers/voice.py`): TTS ElevenLabs → edge-tts, STT Gemini → faster-whisper, with `Fallback*` wrappers and `Null*` degradation; `build_tts`/`build_stt` are env-only. New `voice` MCP server (`synthesize_speech` cached by text hash, `transcribe_audio`, `get_audio`) writes assets under `audio_cache/`. A shared `SpeechEnricher` used by `AgentService` and `NegotiationService` synthesizes audio through the voice MCP after `persist_ui` and attaches `audio_ref` plus a `/speech` data-model object; `hydrate_ui` replays `/speech` with the cached `audioRef`. `POST /api/message` transcribes `audio_b64` via the voice MCP before the agent runs, and `GET /api/audio/{asset_id}` serves the cached bytes. `AgentResponse`/`SavingBagResponse` gained `catalog_id` and `audio_ref`.
- rationale: Accessibility is a product invariant, not a toggle (INV-003), so the catalog decision is deterministic at the persistence seam rather than left to the LLM. Speech rides the data model because A2UI v0.9 has no audio message type; keeping synthesis in one shared post-step avoids double-synthesis across the agent and negotiation flows. Voice is a provider chain like LLM/research (INV-012) and the `voice` MCP server keeps it behind the single door (INV-014).
- impact: Full suite now 132 tests, all passing (25 new). `REQ-ACC-01..06`, `REQ-API-07`, and `REQ-NFR-01` are marked satisfied. Tests are network-free (fake TTS/STT); real ElevenLabs/Gemini calls are not exercised here. `edge-tts` was added to `requirements.txt`; `faster-whisper` is optional and lazy. Frontend must render the accessible catalog styling keyed on `amitie.voz-color.v1` and play `/speech.audioRef`.
- follow_ups: M8 — Caja de Cristal, Kill Test, `DEMO_MODE`, golden-path rehearsal. Rotate any keys exposed during planning (INV-041).

## [2026-09-12] change — M8 Caja de Cristal, Kill Test, and DEMO_MODE
- agent: opencode / deepseek-flash
- requirements: REQ-CC-01, REQ-CC-02, REQ-KT-01, REQ-KT-02, REQ-NFR-04, REQ-NFR-05
- invariants: INV-004, INV-017, INV-019, INV-022, INV-032
- files: `backend/hydration/{assumptions.py,service.py}`, `backend/agent/service.py`, `backend/mcp_servers/ui/{service,server}.py`, `backend/api/schemas.py`, `backend/api/routers/{debug,ui}.py`, `backend/db/{schema.sql,schema.py}`, `backend/ui_contract/{catalog.json,catalog.schema.json}`, `backend/demo/{__init__,golden_path}.py`, `backend/tests/{test_assumptions,test_kill_test,test_demo_mode,test_demo_golden_path}.py`, `backend/tests/test_a2ui_catalog.py`, `A2UI_CATALOG.md`, `SPECS.md`, `AGENTS.md`, `backend/README.md`
- decision: Implemented M8. Caja de Cristal: new `hydration/assumptions.py` derives an `assumptions-section` (`Card` "¿Por qué ves esto?" + `AssumptionChip`s) from the debt simulation inputs and the savings plan inputs; at least one chip is editable and carries `toggle_assumption`, which flows through the existing `/api/action` closed loop so the agent re-simulates and re-emits (REQ-CC-02). Kill Test: `generated_ui.frozen_json` (added with an idempotent `PRAGMA`/`ALTER TABLE` migration in `apply_schema`) stores the first hydrated delivery; `persist_ui` renders and freezes it, and `kill_test`/`GET /debug/kill-test/{surface_id}` serves that blob verbatim with no agent and no live recompute (REQ-KT-01/02, INV-032). DEMO_MODE: graceful degradation only — `AgentService` gains `demo_mode`, and on a provider failure it re-serves the session's last surface (via MCP `get_session` + `hydrate_ui`) instead of erroring; live providers are unaffected when healthy (REQ-NFR-04). Added `demo/golden_path.py` (rehearsal runner) and `tests/test_demo_golden_path.py` (network-free journey across all four beats with a `<90s` assertion). Catalog gained `AssumptionChip` (additive; both catalogs share it).
- rationale: Caja de Cristal and the Kill Test are product features, not slides (INV-004). Freezing at persist and serving the stored blob guarantees the Kill Test cannot be staged (INV-032) while normal delivery still hydrates fresh (INV-022). DEMO_MODE degrades to the last real artifact so a provider outage cannot kill the demo, without disabling live providers.
- impact: Full suite now 139 tests, all passing (7 new). `REQ-CC-01/02`, `REQ-KT-01/02`, `REQ-NFR-04/05` are marked satisfied. The Kill Test test proves the frozen artifact is unaffected by live DB changes. Frontend must render `AssumptionChip` and send `toggle_assumption` actions.
- follow_ups: Operational demo work remains: live golden-path rehearsal with real keys, Cloudflare Tunnel, and the recorded video fallback (REQ-DEMO-04). Rotate any keys exposed during planning (INV-041).

## [2026-09-12] change — provider-failure error contract, DEMO_MODE removal, flat binding reconciliation
- agent: opencode / deepseek-flash
- requirements: REQ-NFR-04 (reworded), REQ-LOOP-01/03..06, REQ-LM-01/02, REQ-UI-01/02, REQ-API-01..04/08, REQ-DATA-01..04, REQ-NFR-02/03
- invariants: INV-004, INV-023
- files: `backend/agent/{service,negotiation}.py`, `backend/api/{app,schemas}.py`, `backend/api/routers/{message,saving_bags}.py`, `backend/config.py`, `backend/.env.example`, `backend/demo/golden_path.py`, `backend/ui_contract/prompt.py`, `A2UI_CATALOG.md`, `SPECS.md`, `AGENTS.md`, `backend/README.md`, `backend/tests/{test_provider_failure,test_bindings_contract}.py`, `backend/tests/{test_a2ui_catalog,test_m3_acceptance}.py` (removed `backend/tests/test_demo_mode.py`)
- decision: Three changes. (1) Provider failures now return a clear, retryable error and never a stale surface. Removed `DEMO_MODE` (config, `.env.example`, `AgentService`), deleted `_cached_response`, and classified failures: `provider_unavailable`/`model_call_limit` are `retryable`, other agent faults are `agent_error`. `AgentResponse`/`SavingBagResponse` gained `error_code` + `retryable`; negotiation and transcription failures return the same shape. HTTP stays 200 with a structured body so the frozen contract is unchanged. (2) Kept the runtime data model **flat** and corrected the docs/prompt that still advertised `/finance/...`: `ui_contract/prompt.py` now lists the canonical root keys, and `A2UI_CATALOG.md` §3/§9 use flat pointers with a literal `TradeoffScale` value (ephemeral control state travels through the action context, not a `/ui` binding). Added `tests/test_bindings_contract.py`, which resolves every delivered `{"path": ...}` against the delivered data model. (3) Ticked the 20 implemented `REQ-*` in `SPECS.md`, marked `REQ-LOOP-02` `[~]` (frontend renderer), and reworded `REQ-NFR-04`.
- rationale: The on-stage destructive test deletes an API key to prove the UI is generated in real time; silently re-serving the last saved surface would look staged and violate INV-004/INV-032. Returning a retryable error lets the frontend show an error screen and retry. The binding mismatch was a latent frontend-breaking bug the offline tests could not catch because the backend never resolves JSON pointers (INV-023: the frontend owns rendering).
- impact: Full suite now 142 tests, all passing (net +3: removed the DEMO_MODE test, added provider-failure and binding-contract tests). `SPECS.md` now reflects reality (backend complete; tunnel, video, and live demo remain). No API version change: errors are still HTTP 200 with `status:"error"`.
- follow_ups: Operational remains: live golden-path rehearsal, Cloudflare Tunnel, recorded video (REQ-DEMO-04), key rotation (INV-041).

## [2026-09-12] fix — real Gemini/DeepSeek tool-calling + provider diagnostics
- agent: opencode / deepseek-flash
- requirements: REQ-NFR-01 (failover), REQ-NFR-05 (golden path)
- invariants: INV-012
- files: `backend/providers/{gemini,deepseek,gateway}.py`, `backend/api/{app,dependencies}.py`, `backend/api/routers/debug.py`, `backend/api/schemas.py`, `backend/demo/golden_path.py`, `backend/tests/{test_providers,test_provider_doctor}.py`, `AGENTS.md`, `backend/README.md`
- decision: Fixed the real-provider tool-calling path and made the golden path self-diagnosing. (1) Gemini rejected `role="tool"` with HTTP 400; `providers/gemini.py::_to_contents` now sends function responses as `Content(role="user", ...)` (the SDK only allows `user`/`model`) and unwraps the tool result JSON into an object. This was the root cause of the live golden-path failure: the first LLM call succeeded, every tool-using turn died with `400 INVALID_ARGUMENT ... Role 'tool' is not supported`, and because a 400 is a `ProviderResponseError` the gateway correctly did not fail over. (2) Fixed the latent DeepSeek linkage: assistant `tool_calls` and tool results now derive the same deterministic id (`call_{name}`), so the documented fallback also works with tools. (3) Added `GET /debug/providers`, which probes the LLM primary and fallback (via new `FallbackLLM.primary`/`.fallback` properties), research grounding, and TTS with minimal real calls and reports per-provider `ok`/latency/error. (4) Rewrote `demo/golden_path.py` to print provider health first, print each step's HTTP status/`status`/`error_code`/`message`/`issues`, skip dependent steps when no surface exists (no more 422 noise), fetch `/debug/trace/{trace_id}` on failure to attribute the provider, and exit non-zero on any failed step instead of only on the time budget.
- rationale: The offline suite uses scripted/fake providers, so it could not catch a vendor request-shape bug; the real run revealed a 100%-reproducible Gemini 400. Fail-fast on response errors is intentional (adapter bugs should be visible, not masked by fallback), so the fix is in the adapter plus explicit diagnostics (INV-012 keeps the failover chain meaningful).
- impact: Full suite now 146 tests, all passing (4 new: Gemini role regression, DeepSeek id linkage, two doctor tests). The golden path now reports `FAILED` with the responsible provider instead of a false `OK`. Live confirmation against real Gemini/ElevenLabs requires the user's environment (network/keys are unavailable to the agent here).
- follow_ups: Re-run the live rehearsal; if `research`/`tts` fail, consider tracing those providers so `/debug/trace` covers them too.

## [2026-09-12] change — New plain-REST finance endpoints (profile/accounts/liabilities) + real "abono" payment tool
- agent: claude-sonnet-5
- requirements: none new (out-of-band addition the frozen `SPECS.md` §8 contract doesn't cover); unblocks the frontend team's REQ-API-* consumers for native (non-A2UI) screens
- invariants: INV-014 (kept: new reads/writes still go through the `finance` MCP server, not raw SQL from the router), INV-015 (kept: balance math lives in `mcp_servers/finance/service.py`, not the LLM)
- files: `backend/mcp_servers/finance/service.py`, `backend/mcp_servers/finance/server.py`, `backend/api/schemas.py`, `backend/api/routers/finance.py` (new), `backend/api/app.py`, `backend/tests/test_finance_tools.py`
- decision: The frontend's Inicio/Préstamos screens render their own native UI (not a generated A2UI surface), so they had no way to reach real data — `SPECS.md` §8's frozen contract is A2UI-only. Added a new `finance` router with `GET /api/profile`, `GET /api/accounts`, `GET /api/liabilities`, and `POST /api/liabilities/{id}/payment`, all backed by new/existing `finance` MCP tools (`get_profile`, new `get_accounts`, existing `get_liabilities`, new `make_payment`) rather than querying SQLite directly from the router, preserving MCP as the only door. `make_payment(user_id, liability_id, amount, account_id?)` is the first real money-movement write in this codebase: it validates the liability is active and the funding account (defaults to the user's checking account) has sufficient balance, then in one `database.batch()` call reduces `liabilities.balance` (marking `status='paid'` if it reaches zero), debits `accounts.balance`, and inserts a `transactions` row (`category='debt_payment'`) — all deterministic arithmetic in `engine`-adjacent service code, never the LLM. Overpaying beyond the remaining balance only debits what was actually owed.
- rationale: The user asked to replace hardcoded frontend cards with real, persisted backend data, and specifically to make the loans panel's inert "Pagar ahora" button (renamed "Abonar" on the frontend) actually do something. `SPECS.md` §12 excludes "payment rails or real money movement" in the sense of external bank transfers/rails, not an internal simulated debt-paydown against seeded liabilities — this is consistent with `engine/planning.py`'s existing `extra_payment` simulation concept, just made real and persisted instead of hypothetical.
- impact: Three previously-hardcoded frontend screens (Inicio balance card, Préstamos list, and now a working Abonar flow) can be wired to real, queryable SQLite state. `tests/test_finance_tools.py` gained `test_make_payment_moves_real_balances` (happy path, overpay-clears-liability, insufficient-funds rejection) but could not be executed in this session — no Python virtualenv with the project's dependencies (`fastapi`, `google-adk`, `mcp`, etc.) exists on this machine; only `python -m py_compile` syntax-checking was possible. New endpoints are not yet reflected in `SPECS.md` §8 (still the A2UI-only frozen contract) — worth a deliberate decision on whether to fold them in formally.
- follow_ups: Run `pytest` for real once a venv exists (`pip install -r backend/requirements.txt`) to confirm `test_make_payment_moves_real_balances` actually passes, not just compiles. Decide whether `GET /api/profile|accounts|liabilities` and `POST /api/liabilities/{id}/payment` should be formally added to `SPECS.md` §8 as a documented (non-A2UI) contract extension, per `INV-051`/`INV-052`'s no-silent-drift rule. Consider an equivalent read endpoint for `saving_bags` list data if the frontend's Apartados screen is wired next (it can already reuse the existing `GET /api/saving-bags`).

## [2026-09-12] change — Environment stood up, live end-to-end verification, and real password authentication (`POST /api/login`)
- agent: claude-sonnet-5
- requirements: REQ-AUTH-01..04 (new, `SPECS.md` §12); confirms REQ-DATA-01/02, REQ-NFR-05, and the finance-endpoint contract note from the previous entry against a real running server, not just syntax-checked
- invariants: INV-040 (kept — no plaintext password stored/logged; local `.env` with placeholder LLM keys stays git-ignored), scope note added to `SPECS.md` §13 (formerly §12) removing "Authentication / authorization systems" from the out-of-scope list with the user's explicit in-session approval
- files: `backend/auth/{__init__.py,passwords.py}` (new), `backend/db/{schema.sql,schema.py,seed.py}`, `backend/api/{schemas.py,app.py}`, `backend/api/routers/{session.py,auth.py (new)}`, `backend/tests/test_auth.py` (new), `backend/.env` (new, local-only, git-ignored), `SPECS.md`
- decision: (1) Created a real Python venv, installed `requirements.txt`, ran `python -m db.init`, and ran the full test suite for real (was previously only `py_compile`-checked) — 147 tests passed, confirming the previous session's `make_payment`/finance-endpoint work was correct, not just syntactically valid. Started the server and exercised `GET /api/profile|accounts|liabilities` and `POST /api/liabilities/{id}/payment` live with `curl` against the real seeded SQLite DB, then re-seeded to restore clean state. Discovered the server can't even start without a non-empty `GEMINI_API_KEY`/`DEEPSEEK_API_KEY` (the provider constructors validate presence eagerly, even though the request path never calls them) — worked around it with a placeholder-valued local `.env` (git-ignored, clearly commented as non-functional placeholders) rather than blocking on real keys the user hadn't provided. (2) Added real password authentication at the user's explicit request: `users` gained `username`/`password_hash`/`password_salt` columns (idempotent `ALTER TABLE` migration in `schema.py`, mirroring the existing `frozen_json` migration pattern) plus a unique index on `username`; `backend/auth/passwords.py` implements stdlib-only PBKDF2-HMAC-SHA256 hashing (200k iterations, per-user random salt, `hmac.compare_digest` for the comparison) — no new dependency. New `POST /api/login` (`backend/api/routers/auth.py`) verifies `{username, password}` against the DB and, on success, creates a session via a helper (`create_session_row`) factored out of the existing `POST /api/session` handler so both paths share one code path; both an unknown username and a wrong password return the same generic `401`, and the username lookup is case-insensitive. The two seeded personas got real, fixed demo credentials: `demo`/`demo1234` → `u_ana`, `accesible`/`demo1234` → `u_don` (replacing the frontend's previous four cosmetic buttons `demo/elderly/blind/lowliteracy`, all of which resolved to the same two backend personas anyway — decided with the user via an explicit question rather than guessed). Seed hashes use fixed, non-secret salts so `db.init` stays byte-for-byte reproducible (REQ-DATA-02).
- rationale: The user asked specifically for a `password` column and, when asked, chose hashed storage and strict enforcement over a decorative column or plaintext — both textbook security defaults, not just "the safer-sounding option." Reusing `create_session_row` instead of duplicating the insert kept `POST /api/session` (still used internally by tests and other flows with no password check) and the new credential-checked path from drifting apart.
- impact: Full suite now 155 tests, all passing (8 new: 3 pure password-hashing unit tests, 5 `TestClient`-level login endpoint tests covering both personas, wrong password, unknown username, and case-insensitivity). Caught and fixed a real ordering bug during live testing (not caught by the fresh-DB unit tests): the new `CREATE UNIQUE INDEX ... ON users(username)` was first placed directly in `schema.sql`, which runs *before* `schema.py`'s idempotent column-migration step — on an already-existing pre-migration DB (exactly this session's dev DB) that index statement failed with `no such column: username`, because the ALTER TABLE that adds the column hadn't run yet at that point in `apply_schema`. Fixed by moving the index creation solely into `_ensure_columns`, after the ALTER TABLE statements, where it belongs. A fresh DB never exhibited the bug (its `CREATE TABLE` already includes the new columns), which is why only live testing against the real, previously-seeded file caught it — a reminder that this backend's own fresh-DB-only test fixtures can miss migration-ordering bugs that only existing/production-shaped databases surface.
- follow_ups: The frontend's login screen (separate repo, `hackmtyfront`) still needs to be pointed at `POST /api/login` instead of its old local mock-credential table — tracked in that repo's own session/changelog. No registration/password-reset/account-lockout flow exists or is planned; this is intentionally the minimum real thing, not a production auth system. Rotate the placeholder `.env` values for real ones before relying on the LLM-driven flows (chat, negotiation, saving bags) — they will fail with a provider auth error until then.
## [2026-09-12] change — isolated voice I/O endpoints (POST /api/stt, POST /api/tts)
- agent: opencode / deepseek-flash
- requirements: REQ-ACC-04, REQ-ACC-05, REQ-API-07
- invariants: INV-012, INV-013, INV-014
- files: `backend/providers/{registry,__init__}.py`, `backend/mcp_servers/voice/{server,service}.py`, `backend/api/{app,schemas}.py`, `backend/api/routers/{voice,__init__}.py`, `backend/tests/test_voice_api.py`, `AGENTS.md`, `backend/README.md`
- decision: Added two diagnostic endpoints that don't involve the agent/LLM, so Gemini STT and ElevenLabs/edge-tts can be tested directly. `POST /api/stt` decodes base64 audio and returns the transcript; `POST /api/tts` synthesizes, caches into `audio_assets` + `audio_cache/`, and returns `{audio_id, audio_ref, provider, mime, bytes, cached}` (or streams the mp3 with `?raw=true`). Both accept an optional `provider` to force one engine instead of the configured chain, so a silent fallback is visible. Registry exposes public `build_tts_provider`/`build_stt_provider` and `build_tts`/`build_stt` gained `provider`/`fallback` overrides; `build_voice_server` takes per-provider option maps and its tools accept `provider`; `create_app` builds those maps from settings (and accepts injected maps for tests).
- rationale: The user needed to feed a local `test.mp3` to Gemini STT and to obtain a playable mp3 from ElevenLabs, but the only existing path ran the full agent turn and never returned the transcript. Forcing a provider makes the ElevenLabs voice-id requirement explicit (the doctor had shown a silent fallback to edge-tts).
- impact: Full suite now 150 tests, all passing (4 new). Endpoints reuse the voice MCP service (cache + `audio_assets`), so `GET /api/audio/{id}` serves what `/api/tts` produces. No change to the agent path.
- follow_ups: ElevenLabs still needs `ELEVENLABS_VOICE_ID` set to actually be exercised; otherwise forcing `provider=elevenlabs` now reports the error instead of degrading.

## [2026-09-12] change — reclassify voice lab as /debug and add ENABLE_DEBUG_ENDPOINTS
- agent: opencode / deepseek-flash
- requirements: REQ-API-08
- invariants: INV-023
- files: `backend/api/routers/voice.py`, `backend/api/app.py`, `backend/config.py`, `backend/.env.example`, `backend/tests/test_voice_api.py`, `SPECS.md`, `AGENTS.md`, `backend/README.md`
- decision: The voice lab endpoints looked like product API. Moved them to `POST /debug/stt` and `POST /debug/tts` with `tags=["debug"]` and an explicit "DEBUG ONLY — not part of the frozen frontend contract" docstring, matching the existing `/debug/*` diagnostics. Added `ENABLE_DEBUG_ENDPOINTS` (default on): when false, `voice.router` and `debug.router` are not included, so every `/debug/*` route (trace, kill-test, providers, stt, tts) disappears from the app and OpenAPI; product routes are unaffected and `POST /api/message` audio STT remains available. Documented the exclusion in `SPECS.md` §8, `AGENTS.md` §11, and the README (product vs diagnostics split, with `curl` examples now under `/debug/*`).
- rationale: With the backend exposed through the public Cloudflare Tunnel, lab endpoints that call paid vendors (e.g. ElevenLabs) must not look like, or be assumed to be part of, the frontend contract (INV-023). The kill switch lets a public run remove them entirely.
- impact: Full suite now 151 tests, all passing (1 new kill-switch test). Endpoint paths changed from `/api/stt`/`/api/tts` to `/debug/stt`/`/debug/tts`; `GET /api/audio/{asset_id}` remains a product route.
- follow_ups: None.

## [2026-09-12] docs — LOANS_CONSULT_GUIDE.md (voice-first loans & credits consult)
- agent: opencode / deepseek-flash
- requirements: none (specification)
- invariants: INV-015, INV-017, INV-023
- files: `backend/LOANS_CONSULT_GUIDE.md`
- decision: Recorded the agreed specification for a voice-first "new loan & credit" consult flow: dedicated `/api/loans/greeting`, `/api/loans/consult`, and `GET /api/loans/{id}` endpoints; a single structured LLM call returning `{response_text, confidence, terminal_response}` with persistence gated at confidence > 0.80; a `loan_requests` table and `generated_ui.entity_id` association; `{{placeholder}}` templates resolved on hydration; audio synthesized every turn; and the hidden `PR_SWITCH` swap (Gemini→DeepSeek, ElevenLabs→local Piper) masked everywhere. Also documents the Gemini thought-signature prerequisite and answers that DeepSeek can generate A2UI via tool/JSON output without delegating to Gemini.
- rationale: The change is large and touches the frozen contract (`SPECS.md` §8), the agent pipeline, providers, schema, and hydration; a single authoritative guide keeps the frontend expectations and the backend behavior aligned and is the reference for the phased implementation.
- impact: Documentation only; no runtime behavior changed. The guide records that the flow is not yet implemented and enumerates the phases, tests, risks, and definition of done.
- follow_ups: Implement phases 0–5; write the `BANK_LOAN_CONTEXT.md` template; amend `SPECS.md`/`AGENTS.md`/`A2UI_CATALOG.md` as the phases land.

## [2026-09-12] feat — execute LOANS_CONSULT_GUIDE (voice-first credit consult)
- agent: opencode / deepseek-flash
- requirements: REQ-API-08b, REQ-NFR-01 (failover), REQ-LM-01 (credit data)
- invariants: INV-012, INV-013, INV-014, INV-015, INV-017, INV-023
- files: `backend/providers/{base,gemini,deepseek,piper,masking,registry,__init__}.py`, `backend/agent/{model,loans,bank_context}.py`, `backend/mcp_servers/finance/{service,server}.py`, `backend/mcp_servers/ui/service.py`, `backend/db/schema.sql`, `backend/api/{app,dependencies,schemas}.py`, `backend/api/routers/{loans,__init__}.py`, `backend/config.py`, `backend/requirements.txt`, `backend/BANK_LOAN_CONTEXT.md`, `backend/tests/{test_providers,test_pr_switch,test_loans_consult}.py`, `SPECS.md`, `AGENTS.md`, `A2UI_CATALOG.md`, `backend/README.md`, `backend/LOANS_CONSULT_GUIDE.md`
- decision: Executed the guide. Phase 0 — fixed Gemini thought signatures: `ToolCall` carries `thought_signature`; the Gemini adapter captures it from candidate parts and echoes the real signature (or `b"skip_thought_signature_validator"`) in `_to_contents`; `agent/model.py` preserves it both ways; model-call budget raised 6→10. Phase 1 — hidden `PR_SWITCH` (default off): under it, the LLM primary is DeepSeek masked as `gemini`, TTS is local `PiperTTS` masked as `elevenlabs`, and STT is faster-whisper masked as `gemini`, via an isolated `AliasedProvider` wrapper that rewrites reported names/models and result `provider` fields. `PiperTTS` lazy-loads `voices/*.onnx` and encodes real mp3 with `lameenc`. Phase 2 — finance `get_credit_history` tool + `agent/bank_context.py` loader + a `BANK_LOAN_CONTEXT.md` template. Phase 3 — `agent/loans.py` `LoansConsultService`: one structured LLM call returning `{response_text, confidence, terminal_response}`, validation with one retry, persistence gated at confidence > 0.80, always-synthesized audio; `persist_ui` now stores the `data_model` snapshot and `hydrate_ui` merges it before resolving `{{placeholders}}`. Phase 4 — `loan_requests` table and `/api/loans/greeting`, `/api/loans/consult`, `GET /api/loans/{loan_request_id}`.
- rationale: The frontend expects a voice-first credit consult with a terminal flag and confidence; the previous agent always produced a UI and never spoke. Keeping the new flow on dedicated endpoints preserves the existing frozen contract (INV-023), the structured single call matches the requested JSON, and the engine still owns any arithmetic (INV-015). The masked `PR_SWITCH` satisfies the owner's cost constraint while keeping the public narrative of Gemini/ElevenLabs.
- impact: Full suite now 165 tests, all passing (Phase 0 signature tests, 7 PR_SWITCH tests, 5 loans tests). `REQ-API-08b` marked satisfied. New deps `piper-tts` and `lameenc` (lazy; app boots without them). `BANK_LOAN_CONTEXT.md` shipped as a fill-in template. Masking is documented as intentionally destroying diagnostics.
- follow_ups: Fill `BANK_LOAN_CONTEXT.md`; install `piper-tts`/`lameenc` and confirm Piper voices for `PR_SWITCH=1`; end-to-end rehearsal of the loans flow with real keys. PR_SWITCH is intentionally not in `.env.example`/README (kept in `LOANS_CONSULT_GUIDE.md`).

## [2026-09-12] feat — local STT via SpeechRecognition (loans audio path)
- agent: opencode / deepseek-flash
- requirements: REQ-ACC-04, REQ-API-08b
- invariants: INV-012, INV-013
- files: `backend/providers/speech_recognition_stt.py`, `backend/providers/registry.py`, `backend/providers/__init__.py`, `backend/config.py`, `backend/.env.example`, `backend/requirements.txt`, `backend/tests/{test_speech_recognition_stt,test_pr_switch}.py`, `backend/LOANS_CONSULT_GUIDE.md`, `AGENTS.md`, `backend/README.md`
- decision: The audio→text step for the loans workflow (and `/api/message`) now supports the `SpeechRecognition` library. New `SpeechRecognitionSTT` transcribes the **audio bytes the frontend sends** (no microphone, so `pyaudio` is intentionally not used), converts mp3→WAV via `pydub` (needs `ffmpeg`), and calls `recognize_google` (engine configurable: google/sphinx/vosk; `STT_LANGUAGE` default es-MX). It is wired as the **local STT under `PR_SWITCH=1`** (replacing faster-whisper, masked as `gemini`) and selectable via `STT_PROVIDER=speech_recognition`. Added `SpeechRecognition`, `audioop-lts` (Python 3.13+ removed `audioop`), and `pydub` to requirements.
- rationale: This satisfies the owner's request to convert received audio with local libraries. Note the chosen engine (Google Web Speech) is an *online* Google call — the library is local, the recognition is not; Vosk/Sphinx are the fully-offline options, switchable by one config value.
- impact: Full suite now 171 tests, all passing (6 new provider tests; PR_SWITCH STT assertion updated from `gemini->faster_whisper` to the masked single `gemini`). `ffmpeg` is a host prerequisite for mp3; without it the adapter degrades with a clear `ProviderUnavailableError`. No regression: 165 pre-existing tests still pass.
- follow_ups: Install `ffmpeg` + the new deps; verify real `recognize_google` transcription of `test.mp3` in your environment; consider Vosk for offline.

## [2026-09-12] change — reconcile invariants/specs with the auth + REST-finance extension
- agent: opencode / deepseek-flash
- requirements: REQ-API-09, REQ-API-10, REQ-API-11, REQ-LOOP-05 (reworded)
- invariants: INV-020 (amended), INV-023 (amended), INV-051/052 (protocol)
- files: `INVARIANTS.md`, `SPECS.md`, `AGENTS.md`, `CHANGELOG.md`
- decision: Reconciled the docs with the auth + plain-REST finance work added by a parallel session. (1) **INV-020**, old: "…no remote or managed database, no auth system." new: "…no remote or managed database. No production/general auth system; a minimal, local, seeded demo login is permitted (no signup, password reset, SSO, or account lifecycle — see SPECS.md §12)." (2) **INV-023**, old: "The backend exposes a frozen REST contract." new: names the two frozen surfaces — A2UI (SPECS §8) and the plain-REST extension (SPECS §8.1). (3) Added **SPECS §8.1** documenting the non-A2UI surface and promoted the finance endpoints to **REQ-API-09** (profile/accounts/liabilities reads), **REQ-API-10** (liability payment), and **REQ-API-11** (`POST /api/login`, cross-referencing REQ-AUTH-01..04). (4) Reworded **REQ-LOOP-05** to scope the "A2UI array" rule to A2UI mutation endpoints, since the REST payment returns domain JSON. (5) Updated `AGENTS.md` layout (`auth/` package, `auth`/`finance` routers) and noted the two surfaces.
- rationale: `INV-051/052` forbid silent drift. The parallel session changed `SPECS.md` scope (auth) and added endpoints without amending the invariants, leaving `INV-020` ("no auth system") contradicting `/api/login`, and `REQ-LOOP-05` contradicting the plain-REST payment. Explicit human approval to reconcile was given in-session.
- impact: Documentation/invariant only; no runtime change. La Mesa's behavior and tests are unaffected. Invariant changes are recorded here per `INV-051`.
- follow_ups: Live golden-path re-verification of La Mesa with real Gemini (validates the thought-signature fix); frontend to point its login screen at `POST /api/login`. Note: `PR_SWITCH` remains undocumented outside `LOANS_CONSULT_GUIDE.md`.

## [2026-09-12] feat — loans: personalized greeting, multipart audio, raw transactions, chart components
- agent: opencode / deepseek-flash
- requirements: REQ-API-08b, REQ-LOOP-05/06 (component additions)
- invariants: INV-016, INV-021, INV-022
- files: `backend/agent/loans.py`, `backend/api/routers/loans.py`, `backend/mcp_servers/finance/service.py`, `backend/ui_contract/{catalog.json,catalog.schema.json}`, `A2UI_CATALOG.md`, `backend/LOANS_CONSULT_GUIDE.md`, `SPECS.md`, `backend/README.md`, `backend/tests/{test_loans_consult,test_finance_tools,test_a2ui_catalog}.py`
- decision: (1) **Greeting personalized**: `greeting` loads `get_profile` and speaks "¿En qué te puedo ayudar hoy, {primer nombre}?" (fallback to a generic line). (2) **Multipart responses**: `POST /api/loans/greeting` and `/consult` now return `multipart/form-data` with a `payload` JSON part and an inline `audio` mp3 part (the service returns `audio_id`; the router reads the cached file). Errors return a payload-only multipart; `GET /api/loans/{id}` stays JSON. (3) **Raw transactions**: `get_credit_history` now includes `recentTransactions` (latest rows) alongside the aggregates, so the model reads real behavior. (4) **Rich UI**: added `LineChart`, `BarChart`, `ForecastChart` to the catalog (json + schema + `A2UI_CATALOG.md`) and a prompt rule that a terminal loans UI must include a forecast/projection chart and a payment schedule.
- rationale: Matches the frontend team's stated expectations (named opening line; mp3 + JSON in one response; grounded in bank context + real behavior; rich forecasts/graphs). Chart additions are additive (catalog ID unchanged) and require frontend implementation.
- impact: Full suite now 182 tests, all passing (new: greeting personalization + multipart parsing; raw-transaction coverage; chart validation). Loans clients must now parse `multipart/form-data` for greeting/consult and implement the three chart components.
- follow_ups: Frontend must implement `LineChart`/`BarChart`/`ForecastChart` and multipart parsing; live verification with real providers still pending.

## [2026-09-12] feat — engine-backed loan insights (kill generic UIs)
- agent: opencode / deepseek-flash
- requirements: REQ-LM-03/07, REQ-API-08b
- invariants: INV-015, INV-016, INV-021
- files: `backend/engine/{amortization,loans_analysis,__init__}.py`, `backend/mcp_servers/finance/{service,server}.py`, `backend/agent/{loans,service}.py`, `backend/ui_contract/{catalog.json,catalog.schema.json}`, `A2UI_CATALOG.md`, `backend/BANK_LOAN_CONTEXT.md`, `backend/LOANS_CONSULT_GUIDE.md`, `backend/README.md`, `backend/tests/{test_loans_analysis,test_loans_consult,test_finance_tools,test_agent_instructions,test_a2ui_catalog}.py`
- decision: The loans turn previously asked the model for forecast charts with no engine data, so it had to invent numbers (generic dashboards + an `INV-015` violation). Fixed by computing everything deterministically and injecting it. (1) `engine/amortization.simulate` now records **per-liability payoff months** (defaulted field). (2) New `engine/loans_analysis.analyze` produces user-specific insights from the user's own liabilities/transactions/subscriptions: baseline vs accelerated **scenarios** (monthly payment, payoff months, total interest, interest/months saved), avalanche vs snowball, `payoffOrder`, `highCost`, **behavior** (subscription load + share of income, expense volatility, average surplus, month-over-month category movers), **quincena** pressure, and a `nextBestAction` (target creditor + recommended extra = surplus or the subscription leak, with measured effect). (3) New finance MCP tool `analyze_loans`; the loans service injects its JSON into the prompt. (4) Added `ScenarioComparison` to the catalog and an explicit **insight mandate** to the loans prompt and the La Mesa `UI_DESCRIPTION`: include ScenarioComparison, name the first credit to attack with APR, propose a concrete action with a measured effect, cite subscriptions/quincena, forbid generic advice and invented figures. (5) Drafted a concrete `BANK_LOAN_CONTEXT.md` (products/rates/eligibility/tone).
- rationale: Winning requires non-generic, genuinely useful output; `INV-015` requires the engine to own the math. This also closes the contradiction where the model was told not to compute amortization but was expected to render a forecast.
- impact: Full suite now 187 tests, all passing (new: deterministic analysis, `analyze_loans` tool, prompt-injection capture, agent-instruction guards, `ScenarioComparison` validation). La Mesa's debt flow now uses `analyze_loans` for engine-backed, user-specific surfaces.
- follow_ups: Frontend must implement `ScenarioComparison` (additive; catalog ID unchanged) and the already-noted charts; review/edit `BANK_LOAN_CONTEXT.md`; live verification with real providers still pending.

## [2026-09-12] docs — API_KNOWLEDGE.md (AI-only frontend contract manual)
- agent: opencode / deepseek-flash
- requirements: REQ-API-01..11, REQ-ACC-03
- invariants: INV-016, INV-017, INV-023
- files: `API_KNOWLEDGE.md`, `CHANGELOG.md`
- decision: Wrote a self-contained, AI-only contract manual for the React frontend AI covering all 21 frontend-facing routes (auth, native REST, chat/La Mesa, loans multipart, El Revés, saving bags, audio) plus a `/debug/*` appendix marked not-for-UI. It documents the A2UI v0.9 flat message model, bindings, catalogs, the full component/action reference, the `/speech` convention, error codes and HTTP semantics, Spanish-UX rules, end-to-end playbooks, a TypeScript types appendix, and a quick-reference table. The document is in English but mandates that all user-facing strings/audio are Spanish (`es-MX`) and that backend Spanish text is rendered verbatim.
- rationale: The frontend team (and its AI) previously had to infer the contract from `SPECS.md`, `A2UI_CATALOG.md`, and code; a single authoritative machine-oriented manual reduces integration errors and encodes the interaction protocol precisely (hydration, multipart loans, terminal_response semantics, accessible catalog).
- impact: Documentation only; no runtime change. Suite unaffected.
- follow_ups: Keep `API_KNOWLEDGE.md` in sync if the contract changes (multipart, `ScenarioComparison`, new endpoints).

## [2026-09-12] change — Saving Bags disabled + docs scrubbed (PENDING TO BE RELEASED)
- agent: opencode / deepseek-flash
- requirements: REQ-BAG-01..08, REQ-API-05 (deferred)
- invariants: INV-002 (amended), INV-014 (amended), INV-021 (amended), INV-030 (amended), INV-051/052 (protocol)
- files: `INVARIANTS.md`, `SPECS.md`, `AGENTS.md`, `API_KNOWLEDGE.md`, `A2UI_CATALOG.md`, `backend/README.md`, `backend/LOANS_CONSULT_GUIDE.md`, `backend/api/{app.py,routers/__init__.py}`, `backend/agent/service.py`, `backend/mcp_servers/ui/service.py`, `backend/hydration/{service,assumptions}.py`, `backend/ui_contract/prompt.py`, `backend/engine/__init__.py`, `backend/tests/{test_bindings_contract,test_assumptions}.py` (removed savings tests: `test_savings_engine`, `test_savings_tools`, `test_hydration_savings`, `test_m6_acceptance`)
- decision: Saving Bags is stale, so it was **disabled from the shipped surface and scrubbed from the docs**, marked **PENDING TO BE RELEASED**. (1) Code unwired: removed the `saving_bags` router and the `savings` MCP server from the app/toolbox; removed the "FLUJO AHORRO" instruction from `agent/service.py`; removed the `saving_bag` hydration branch, the savings revalidation/assumptions, the `savings` root key from the prompt, and the savings engine exports. Modules (`engine/savings.py`, `mcp_servers/savings/`, `api/routers/saving_bags.py`, `api/schemas.py` saving models) and DB tables/seed are **retained dormant** on disk. (2) Docs: replaced the Saving Bags sections in `SPECS.md` (§3, `REQ-API-05`), `API_KNOWLEDGE.md` (§8 + playbook D + quick-ref + TS), `AGENTS.md` (pillar), `backend/README.md`, `A2UI_CATALOG.md` (`CashFlowTimeline`/`GoalJar` reserved), and `LOANS_CONSULT_GUIDE.md` with a clear pending marker. (3) **INV-002** old: "Saving Bags is the second pillar. It must ship…" new: "Saving Bags is PENDING TO BE RELEASED (staged, not shipped)…"; **INV-030** old hard-cut list included "one Saving Bag" new: "two La Mesa mutation moments, El Revés, the voice-first Loans & Credits consult, and one accessible persona"; recorded here per `INV-051`. Also amended **INV-014** (MCP server list drops `savings` → staged) and **INV-021** (persisted-UI domain drops `saving_bag` → pending).
- rationale: The user declared the current Saving Bags implementation stale and requested it be removed from information and marked pending to avoid the frontend AI building against it. Keeping the code dormant preserves the work for a future release while guaranteeing it is not reachable or documented as shipped.
- impact: Full suite now 171 tests, all passing (16 savings-specific tests removed; app boots, `/api/saving-bags*` no longer registered, the agent no longer offers savings). Research/grounding provider kept (still named in `INV-012`, probed by `/debug/providers`). Catalog JSON/schema unchanged (additive; `CashFlowTimeline`/`GoalJar`/`refresh_bag`/`adjust_goal` remain reserved). DB tables and the seeded travel bag remain but unused.
- follow_ups: When reviving, re-wire the router/server, restore the agent instruction + hydration, re-add the savings tests, and flip the pending markers; also confirm the research provider is still the right fallback owner.

## [2026-09-12] feat — engine-backed loan offer, risk panel, and manual loan creation
- agent: opencode / deepseek-flash
- requirements: REQ-LM-10, REQ-API-08b, REQ-API-08c
- invariants: INV-014, INV-015, INV-021
- files: `backend/engine/{loan_offer,__init__}.py`, `backend/db/{schema.sql,schema.py,seed.py}`, `backend/mcp_servers/finance/{service,server}.py`, `backend/agent/loans.py`, `backend/api/{schemas.py,routers/loans.py,app.py}`, `backend/ui_contract/{catalog.json,catalog.schema.json,voz_color.json}`, `backend/config.py`, `backend/.env.example`, `A2UI_CATALOG.md`, `API_KNOWLEDGE.md`, `SPECS.md`, `backend/README.md`, `backend/LOANS_CONSULT_GUIDE.md`, `backend/tests/{test_loan_offer,test_finance_tools,test_loans_consult,test_a2ui_catalog,test_catalog_voz_color}.py`
- decision: Closed three gaps in the loans flow. (1) **Deterministic offer** (`engine/loan_offer.py`): `propose_offer` derives the **backend-proposed amount** from affordability (DTI cap vs `income*cap − minPayment` and the actual surplus), computes annuity terms, an **IRR-based CAT** including opening/insurance fees, a per-month `schedule[]`, and a full **risk panel** — DTI, disposable surplus (income − normalized subscriptions − min payments − avg 3–6mo `out` spend), liquidity buffer (Σ accounts ÷ avg spend), relative cost vs existing APRs and `lender_policies.apr_floor`, income stability (CV), payroll-deduction net per period, **savings-goal delay** (retained `saving_bags` data), and a **payment-history** score projection. Defaults are env-configurable (`LOAN_DEFAULT_APR/TERM_MONTHS/OPENING_FEE_PCT/INSURANCE_FEE_PCT/DTI_CAP`). (2) **Canonical contract**: added the required `LoanOffer` component (`amount, apr, months, monthlyPayment, totalInterest, cat, totalCost, schedule`) and `request_loan` action; the consult injects the offer into `/loan`, requires `LoanOffer`, and **resolves `/loan/*` bindings** so the amount is always numeric; `_persist_terminal` returns the **hydrated** terminal UI and enforces the guarantee. (3) **Manual creation**: new `loans`, `loan_offers`, `payment_history` tables (+ liability fee/CAT columns, idempotent migration) and `POST /api/loans`, which validates against the stored offer and atomically inserts the loan **and disburses** (credits checking + `loan_disbursement`). Generation never creates a loan.
- rationale: The user required a behavior-based offer that the user can actually pay, a guaranteed extractable amount, and explicit user consent before creating the loan. All numbers are engine-computed (`INV-015`); the LLM only presents them. `LoanOffer` + `/loan` give the frontend a stable extraction path.
- impact: Full suite now 177 tests, all passing (new: engine offer/CAT/risk, `compute_loan_offer`/`create_loan` tools, terminal `LoanOffer` guarantee, manual create + disbursement). New tables migrate existing DBs. The catalog gained `LoanOffer`/`request_loan` (additive; both catalogs).
- follow_ups: Frontend must implement `LoanOffer` and the `request_loan` → `POST /api/loans` decision; live verification with real providers still pending.

## [2026-09-12] docs — API_KNOWLEDGE.md loan clarifications
- agent: opencode / deepseek-flash
- requirements: REQ-API-08b, REQ-API-08c, REQ-LM-10
- invariants: INV-015, INV-023
- files: `API_KNOWLEDGE.md`
- decision: Clarified the frontend contract for the new loan flow: (1) `request_loan` is **client-routed** — it must go to `POST /api/loans`, never `POST /api/action`; (2) documented the not-affordable case (`amount = 0` → `terminal_response` stays `null`, no offer to render); (3) documented the full `/loan/risk` panel shape and `warnings[]`; (4) labeled `cat` as an approximate IRR-based cost, not the official Banxico CAT; (5) distinguished `loan_request_id` (consult) from `loans.id` (actual credit); (6) extended the `400` status row to cover `POST /api/loans`; (7) added a `LoanRisk` TypeScript interface.
- rationale: Prevent the frontend AI from mis-routing `request_loan` or misreading the offer, and give it the exact risk fields to render the behavior-based insights.
- impact: Documentation only; no runtime change. Suite unaffected (177 tests).
- follow_ups: None.
## [2026-09-12] change — real transfers backend (saved recipients + own/external transfer)
- agent: claude-code / claude-sonnet-5
- requirements: REQ-XFER-01, REQ-XFER-02, REQ-XFER-03, REQ-XFER-04
- invariants: INV-014 (MCP-only persistence), INV-015 (deterministic money math, LLM never touches it), INV-023 (frozen contract additivity)
- files: `backend/db/schema.sql`, `backend/db/schema.py`, `backend/mcp_servers/finance/clabe.py` (new), `backend/mcp_servers/finance/service.py`, `backend/mcp_servers/finance/server.py`, `backend/api/schemas.py`, `backend/api/routers/finance.py`, `backend/tests/test_schema.py`, `backend/tests/test_transfer_tools.py` (new), `SPECS.md`
- decision: Implemented the backend half of `hackmtyfront/openspec/changes/redesign-transfers-real-data` — the native Transferencias screen's real-data backend contract. Added a `saved_recipients` table (`id, user_id, alias, clabe, bank_name, created_at` + index on `user_id`) and an idempotent `transactions.memo` column migration, both following the existing `_ensure_columns`/`frozen_json` pattern exactly. Added a server-side CLABE checksum validator (`mcp_servers/finance/clabe.py`, mod-10 with weights 3-7-1 repeating) that mirrors the frontend's `src/features/transfers/clabe.ts` algorithm bit-for-bit — verified against the same known-good/known-bad CLABE fixtures the frontend mocks use. New `finance` MCP tools `list_recipients`, `create_recipient`, `transfer_funds` follow `make_payment`'s exact shape: a single deterministic `database.batch()` write, `{status, issues}` on rejection, never trusting client-only validation. `transfer_funds` handles two destination kinds: `own` (validates the destination account belongs to the same user and differs from source, then debits source + credits destination + inserts two `transactions` rows, `category='transfer_own'`) and `external` (re-validates the CLABE checksum, debits source only, inserts one `transactions` row `category='transfer_external'`, and optionally persists a new `saved_recipients` row when `save_recipient` is set). New plain-REST routes `GET/POST /api/recipients` and `POST /api/transfers` in `api/routers/finance.py`, with `TransferRequest.destination` modeled as a pydantic discriminated union (`kind: "own" | "external"`) mirroring `PaymentResponse`'s status/issues convention exactly so the frontend's existing `ApiError`/`issues` handling (`AbonoModal`) applies unchanged.
- rationale: The Transferencias screen was the last screen in the app whose actions had zero lasting effect (100% mocked balance/recipients, `setTimeout` + random decline). The rest of the native screens (Inicio, Préstamos "Abonar") already treat the seeded SQLite accounts as the real source of truth; this closes that gap using the exact pattern already established and tested for "Abonar," rather than inventing a new one.
- impact: Full suite now 187 tests, all passing (16 new: 7 transfer-tool tests in `test_transfer_tools.py`, plus `test_schema.py`'s `saved_recipients` table assertion). Verified all three new endpoints end-to-end with `curl` (recipient create/list with a valid and an invalid CLABE; an own-account transfer moving both balances; an external transfer with `save_recipient=true`; insufficient funds, invalid CLABE, and same-account-both-sides all correctly rejected with 400) — against an isolated seeded copy of the local SQLite DB, not `backend/data/amitie.sqlite3` directly, because another uvicorn instance was already running against that shared file for unrelated in-progress work; the shared file was left untouched (confirmed via that other running instance's own `/api/accounts` response before and after). `SPECS.md` gained a new §13 ("Real transfers"), and the previous §13 ("Explicitly out of scope") was renumbered to §14 — the same renumbering pattern already used when §12 ("Real login") was inserted (see the 2026-09-12 auth entry above, `SPECS.md §13 (formerly §12)`).
- follow_ups: The frontend half (`app/transferir*.tsx`, `transfer.store.ts`, `clabe.ts` tightening, API types/endpoints) is implemented in the same pass in `hackmtyfront` — see that repo's own commit/PR for the client side of this contract. No manual multi-terminal `curl` rehearsal was done with a live, currently-open frontend session (none was running); the isolated-copy verification above stands in for it.

## [2026-09-12] change — audience-adaptive interface complexity (education, age, activity)
- agent: opencode / deepseek-flash
- requirements: REQ-LM-11
- invariants: INV-015 (deterministic classification, LLM never decides), INV-023 (additive contract surface)
- files: `backend/engine/audience.py` (new), `backend/engine/__init__.py`, `backend/db/schema.sql`, `backend/db/schema.py`, `backend/db/seed.py`, `backend/mcp_servers/finance/service.py`, `backend/mcp_servers/finance/server.py`, `backend/mcp_servers/ui/service.py`, `backend/agent/loans.py`, `backend/agent/service.py`, `backend/tests/test_audience.py` (new), `backend/tests/test_finance_tools.py`, `backend/tests/test_loans_consult.py`, `SPECS.md`, `API_KNOWLEDGE.md`, `A2UI_CATALOG.md`, `AGENTS.md`
- decision: The generated UI now adapts its complexity to the user's comprehension instead of always emitting the dense panel. Added `users.education_level` (last obtained degree; `licenciatura` for `u_ana`, `primaria` for `u_don`) with an idempotent migration, returned by `get_profile`. Added a pure `engine/audience.py` classifier that returns `simple | standard | detailed` (plus `comprehension`, `financialSophistication`, `explainTerms`, `showAdvancedMetrics`, `showCharts`, `maxSections` and a Spanish `directive`) from age, accessibility mode, education and real activity (transaction count, distinct categories, accounts/liabilities/subscriptions). Exposed via a new `finance` MCP tool `get_audience(user_id)`; `persist_ui` computes it and every hydrated surface carries it at `/audience`. The loans `_system_prompt(audience)` and the La Mesa `UI_DESCRIPTION` now follow the directive: `simple` = plain language, max two sections, no CAT/DTI/risk/ScenarioComparison; `standard` = current mandate; `detailed` = full CAT/DTI/risk/charts. `LoanOffer.amount` remains mandatory at every level (validation now also rejects a `LoanOffer` without a numeric/`/loan/` amount).
- rationale: A 71-year-old with `low_literacy` and low transaction volume was receiving the same information-dense UI as a 32-year-old with a degree and five liabilities, which contradicts pillar 2 (adaptability of the generated UI). The audience must be a deterministic backend decision so the LLM cannot silently drop required content (e.g. the loan amount).
- impact: Loans terminals for `u_don` are classified `simple` and for `u_ana` `detailed`; both still include a numeric `LoanOffer.amount`. Suite extended with `test_audience.py` (5 cases) plus assertions in `test_finance_tools.py`/`test_loans_consult.py`.
- follow_ups: Frontend may optionally use `/audience` to tune density (no new component required). Live verification with real providers still pending.

## [2026-09-12] change — five showcase personas (distinct audiences/catalogs) + reseeded local DB
- agent: opencode / deepseek-flash
- requirements: REQ-AUTH-04, REQ-DATA-01, REQ-DATA-02, REQ-LM-11
- invariants: INV-015 (deterministic seed), INV-019 (persistence port), INV-023 (no contract change)
- files: `backend/db/seed.py`, `backend/tests/test_seed.py`, `backend/tests/test_local_sqlite.py`, `SPECS.md`, `API_KNOWLEDGE.md`, `backend/data/amitie.sqlite3` (reseeded)
- decision: Expanded the seed from 2 to 5 personas so the demo can show three distinct audience levels and both catalogs, and reseeded the existing local database (`python -m db.init`). Added `_txn_rows()` (data-driven deterministic transaction generator) and `_new_persona_transactions()`; new users `u_sofia` (Sofía Ramírez, 26, `tecnico`, 1 card) → `standard`, `u_carmen` (Carmen Ruiz, 58, `secundaria`, 2 debts, standard catalog) → `simple`, and `u_roberto` (Roberto Díaz, 45, `maestria`, high income, 1 auto loan) → `detailed`. Existing `u_ana` (`detailed`, over-indebted) and `u_don` (`low_literacy` → `simple`, voz-color + speech) are unchanged so the golden path and engine tests stay valid. All five log in with password `demo1234`; usernames `demo`, `roberto`, `sofia`, `carmen`, `accesible`. Transactions total 294 (was 96). Test expectations updated (`test_seed.py`, `test_local_sqlite.py`).
- rationale: The product thesis is that the agent generates a UI adapted to the user; a single over-indebted persona could not demonstrate that. Five contrasting profiles make `simple`/`standard`/`detailed` and standard-vs-voz-color observable in one session, and keep the audience classifier exercised on real seeded data.
- impact: `python -m db.init` now yields 5 users / 294 transactions; full suite 190 tests passing. Live login verified for all five against `./data/amitie.sqlite3`. `u_don` has no liabilities/transactions (kept intentionally) so the `simple` accessible path stays clean and the loan-offer test remains valid.
- follow_ups: Frontend login screen should surface the 5 credentials; the demo script should pick the persona that matches the UI being showcased.

## [2026-09-12] feat — OpenAPI and Swagger UI endpoints
- agent: antigravity / gemini-3.8-flash
- requirements: none
- invariants: INV-010, INV-023
- files: `backend/api/app.py`, `backend/tests/test_openapi_swagger.py`, `CHANGELOG.md`
- decision: Added dedicated interactive Swagger UI and OpenAPI documentation endpoints:
  - `GET /swagger` and `GET /swagger/` (as well as `GET /api/swagger`) serving interactive Swagger UI HTML via `get_swagger_ui_html`.
  - `GET /openapi` and `GET /api/openapi` (as well as `GET /api/openapi.json` and standard `GET /openapi.json`) returning the generated OpenAPI schema JSON.
  - Configured `FastAPI` instance with title, description, version, `openapi_url="/openapi.json"`, `docs_url="/docs"`, and `redoc_url="/redoc"`.
  - Configured `.pth` in `.venv` so `uvicorn api.main:app --reload` runs cleanly from both the repository root and `backend/`.
- rationale: Developer and judge tooling convenience: by default FastAPI only served Swagger UI at `/docs` (and `/swagger` returned 404), while OpenAPI was only at `/openapi.json`. Adding these explicit endpoints allows direct access to Swagger UI via `/swagger` and `/api/swagger`, and schema inspection via `/openapi`.
- impact: Suite expanded from 190 to 198 tests, all passing.
- follow_ups: none

## [2026-09-12] feat — structured logging with structlog + trace_id propagation
- agent: antigravity / gemini-3.8-flash
- requirements: none
- invariants: INV-018
- files: `backend/requirements.txt`, `backend/config.py`, `backend/observability/logging_config.py`, `backend/observability/logging.py`, `backend/observability/context.py`, `backend/observability/middleware.py`, `backend/observability/__init__.py`, `backend/api/app.py`, `backend/providers/gateway.py`, `backend/db/init.py`, `backend/agent/{service,negotiation,loans}.py`, `backend/tests/test_structured_logging.py`, `CHANGELOG.md`
- decision: Implemented structured logging with `structlog` aligned with `AGENTS.md` §6, §8 and `INV-018`:
  - Created `observability/logging_config.py`: sets up `structlog` processors (`merge_contextvars`, `add_logger_name`, `add_log_level`, ISO timestamps, stack/exc formatting, and `_redact_sensitive_fields` defending against leaking API keys, passwords, raw audio, and financial payloads).
  - Production mode (`APP_ENV=production`) outputs JSON logs; development mode (`APP_ENV=development`) outputs readable console logs.
  - Standard library compatibility: `structlog.stdlib.ProcessorFormatter` with `foreign_pre_chain` ensures standard loggers (`uvicorn`, `httpx`, Google ADK, MCP SDK) produce the same structured format with `trace_id`.
  - Configured `TraceMiddleware` and `trace_context` to bind incoming `x-trace-id` (or generated trace ID), `path`, and `method` into `structlog.contextvars`.
  - Configured `lifespan` in `api/app.py` to initialize logging and log `backend_started` / `backend_stopped`.
  - Replaced `print()` in `db/init.py` with structured logger.
  - Added structured instrumentation in `agent/service.py`, `agent/negotiation.py`, `agent/loans.py`, and `providers/gateway.py`.
- rationale: Fulfilled `AGENTS.md` §6 mandate ("Logging: structured logging only. Never `print`. Never log secrets, raw audio, or full financial payloads.") and integrated with the existing `trace_id` pipeline.
- impact: Suite expanded from 198 to 204 tests, all passing. No regressions across any existing tests.
- follow_ups: none


## [2026-09-13] fix — loans consult: normalize-then-validate + 5s deadline with deterministic fallback
- agent: opencode / deepseek-flash
- requirements: REQ-LM-12, REQ-LM-13
- invariants: INV-010 (HTTP only; no sockets), INV-015 (deterministic math/classification)
- files: `backend/ui_contract/normalize.py` (new), `backend/agent/loans_fallback.py` (new), `backend/agent/loans.py`, `backend/api/app.py`, `backend/config.py`, `backend/providers/{base,deepseek,gemini,gateway}.py`, `backend/.env.example`, `backend/tests/test_normalize.py` (new), `backend/tests/test_loans_consult.py`, `backend/tests/test_providers.py`, 16 test doubles, `SPECS.md`, `API_KNOWLEDGE.md`, `A2UI_CATALOG.md`, `backend/LOANS_CONSULT_GUIDE.md`
- decision: Fixed the loans consult's silent failures and latency. Root cause confirmed from stored traces: the loans prompt told the model to emit `action` as a string and numeric `LoanOffer` props as `{{...}}` placeholders, while `_validate_terminal` ran the strict A2UI JSON schema on the raw template (which rejects both), so both attempts failed and the endpoint returned `{status:"error", error_code:"agent_error"}` with HTTP 200 — and the mobile client rendered nothing. Added pure `ui_contract/normalize.py` (bare action name → `{"event":{"name":...,"context":{}}}`; whole-placeholder numeric/boolean prop → `{"path": ...}`; numeric strings coerced) and normalize before validate/persist. Reworked `consult` to a **single** attempt wrapped in `asyncio.wait_for` (`LOANS_LLM_DEADLINE_SECONDS=4.0`) with per-call `max_tokens` (`LOANS_MAX_TOKENS=900`, threaded through the provider Protocol → deepseek/gemini/gateway), and a deterministic engine-built terminal (`agent/loans_fallback.py`) on timeout/provider error/invalid output/low-confidence terminal. Compacted the injected credit history (dropped raw transactions) and constrained the terminal to the mobile-supported component subset. Not-eligible (`amount<=0`) still returns `terminal_response=null` + explanatory text.
- rationale: The requirement is a hard ≤5 s consult. LLM latency is variable and the retry loop doubled it; validation must accept the shapes the prompt actually produces. Normalizing first keeps the agent generating the UI while guaranteeing schema validity, and the deterministic fallback guarantees the SLA (and never leaves the user with a silent error).
- impact: Suite now 199 tests, all passing (added `test_normalize.py`; loans tests now cover normalization, missing-LoanOffer fallback, and a forced LLM timeout returning a fallback terminal). `demo`/`u_ana` is intentionally not eligible (documented); offer demos use `roberto`/`sofia`/`carmen`. No invariant changed; HTTP/REST contract intact.
- follow_ups: Mobile side implemented in `hackmtyfront` (see its OpenSpec change `harden-loans-consult-sync`); live re-verification with the real DeepSeek key pending.

## [2026-09-13] change — POST /api/agent/greeting (deterministic spoken greeting for the Asistente tab)
- agent: opencode / deepseek-flash
- requirements: REQ-API-12
- invariants: INV-014 (MCP-only data/voice), INV-015 (no LLM in the greeting path)
- files: `backend/agent/service.py`, `backend/api/routers/agent.py` (new), `backend/api/schemas.py`, `backend/api/app.py`, `backend/tests/test_agent_greeting.py` (new), `SPECS.md`, `API_KNOWLEDGE.md`
- decision: Added `POST /api/agent/greeting` taking `{session_id}`, validating the session, and returning an `AgentResponse` with a personalized, deterministic `assistant_text` (no LLM) plus `audio_ref` for accessible users only. `AgentService.greeting` reads the profile through the finance MCP (`get_profile`) for name + `accessibilityMode`, and calls `synthesize_speech` only when the mode is non-null, mirroring the voz-color autoplay contrast. Standard users get text with `audio_ref: null`.
- rationale: The Asistente tab had no way to speak first — the only initial turn logic required an `intent` param, so a plain tab open produced no `/api/message` and no greeting audio. A dedicated deterministic endpoint (parallel to `/api/loans/greeting`) is faster and more reliable than abusing the agent with a synthetic message, and keeps audio generation behind the voice MCP.
- impact: Suite extended with `test_agent_greeting.py` (accessible → `audio_ref`; standard → none; unknown session → 404). The frontend calls it on the Asistente tab open (see the frontend repo's `add-assistant-initial-greeting` change).
- follow_ups: Frontend wiring + auto-play; live verification with the real Piper/ElevenLabs chain.

## [2026-09-13] change — the assistant's name is now Luna (feminine)
- agent: opencode / deepseek-flash
- requirements: none (branding/persona)
- invariants: none
- files: `backend/agent/service.py`, `backend/agent/loans.py`, `backend/api/routers/debug.py`, `backend/BANK_LOAN_CONTEXT.md`, `backend/mcp_servers/finance/service.py`, `backend/tests/test_agent_greeting.py`, `backend/tests/test_loans_consult.py`
- decision: Renamed the AI persona from "La Mesa" to "Luna" in the AI-facing code only, and made all self-reference feminine. `ROLE_DESCRIPTION` and the loans `_system_prompt` now say "Eres Luna, una agente/asesora…" plus an explicit identity line ("Tu nombre es Luna. Eres femenina; si te presentas usa el femenino…"), the deterministic and loans greetings say "Soy Luna, tu asesora de crédito", the debug TTS sample says Luna, and the injected `BANK_LOAN_CONTEXT.md` product is now "Crédito personal" (disbursement label likewise). The internal flow label dropped to "FLUJO DEUDA".
- rationale: The product chose a unique feminine assistant name; keeping the change to persona/prompt strings avoids churn in app metadata, docs, and internal identifiers while ensuring the model never introduces itself as any other name.
- impact: Backend suite extended with persona assertions (`test_agent_greeting.py`, `test_loans_consult.py`); full suite 216 passing. Explicitly unchanged: `APP_NAME`/`AGENT_NAME="lamina"`, the FastAPI title/description and their swagger tests, docs/CHANGELOGs, the research sub-prompt.
- follow_ups: None.

## [2026-09-13] fix — TTS reads grouped numbers naturally (spoken-text normalization)
- agent: opencode / deepseek-flash
- requirements: REQ-ACC-03, REQ-ACC-05 (behavior only; no contract change)
- invariants: none
- files: `backend/providers/speech_text.py`, `backend/mcp_servers/voice/service.py`, `backend/tests/test_speech_text.py`, `backend/tests/test_voice_tools.py`, `A2UI_CATALOG.md`
- decision: The AI formats amounts with digit-grouping separators (e.g. `$7,000`). The underlying engines, notably the local Piper/espeak-ng path (`PR_SWITCH=1`), read the comma literally and spell the digits — "7,000" → "siete, cero cero cero" instead of "siete mil". Added a pure `providers/speech_text.py::normalize_for_speech` that removes only a comma between digits that introduces a three-digit group (`7,000` → `7000`, `1,234,567` → `1234567`); conservative rules leave `12,34` and `1,2345` untouched, and it is idempotent and a no-op on plain text. Applied it at the single TTS choke point (`mcp_servers/voice/service.py::synthesize_speech`) just before `tts.synthesize(...)`. Deliberately scoped: only grouping separators, no currency/percent/number-to-words; `$`, `%`, and ranges are left to the engine.
- rationale: One central transform fixes every TTS flow (loans `response_text`, accessible surface speech, greeting, `/api/tts`) with no provider or frontend change. Normalizing only at the provider boundary — while hashing and storing the original text — keeps the `audio_cache` key stable and preserves `response_text`/`/speech.text` for display; `hydrate_ui`'s `speech_hash` lookup keeps matching. Full number-to-words was rejected as unnecessary: all engines read a plain cardinal correctly. This fixes a frontend-visible pronunciation bug without touching the AI's formatted output.
- impact: New pure test module `tests/test_speech_text.py`; `tests/test_voice_tools.py` now asserts the provider receives `"Cuesta $7000 al mes"` while `get_audio` still returns `"Cuesta $7,000 al mes"` and repeats stay cached (full suite green). `"7,000"` and `"7000"` produce distinct cache entries but identical audio. `A2UI_CATALOG.md` §11 documents that spoken numbers are normalized only for synthesis.
- follow_ups: If a future engine still mangles currency/percent/ranges, extend `normalize_for_speech` (currency/percent expansion or number-to-words) at the same choke point.

## [2026-09-13] fix — TTS speaks amounts as "mil pesos" (currency + cache invalidation)
- agent: opencode / deepseek-flash
- requirements: REQ-ACC-03, REQ-ACC-05 (behavior only; no contract change)
- invariants: none
- files: `backend/providers/speech_text.py`, `backend/mcp_servers/voice/service.py`, `backend/tests/test_speech_text.py`, `backend/tests/test_voice_tools.py`, `A2UI_CATALOG.md`
- decision: The prior fix only stripped grouping commas, so `$1,000.00` still came out as "dólar mil punto cero cero" (and stale cached audio kept playing the even older "dólar uno coma..."). Two changes: (1) extended `normalize_for_speech` to rewrite the actual spoken form — numeric ranges (`–`/`—` between digits/`%`) to " a ", drop trailing `.00`, `$<n>` (optionally followed by `pesos`/`MXN`) to `<n> pesos`, standalone `MXN` to `pesos`, collapse `pesos pesos`, keep the grouping-comma strip, collapse double spaces. Verified against the bundled espeak-ng `es-419` phonemizer that Piper uses: `$1,000.00`→`1000 pesos`→"mil pesos", `$5,000–$200,000`→"cinco mil pesos a doscientos mil pesos", `18%–36%`→"dieciocho por ciento a treinta y seis por ciento"; prose dashes left untouched. (2) `text_hash` now keys on the normalized spoken form plus a `speech-v2` version tag, so all previously cached assets (including the stale `"…Soy La Mesa…"` greeting) are ignored and regenerated. The stored `audio_assets.text`, `/speech.text`, and `GET /api/audio` metadata keep the original formatting for display.
- rationale: The root cause of "the issue persists" was the cache: because the hash stayed on the original text, every pre-fix phrase was still served unchanged. Hashing the spoken form makes cache identity equal what is actually synthesized, so a normalization change self-invalidates. Currency is always spoken as "pesos" (es-MX app) and decimals as "punto", per user decision; the display text is untouched ("the AI is right").
- impact: New pure cases in `tests/test_speech_text.py`; `tests/test_voice_tools.py` asserts the provider receives `"Cuesta 7000 pesos al mes"` while `get_audio` returns `"Cuesta $7,000.00 al mes"`, and that `"$1,000.00"` and `"1000 pesos"` share one cache entry (full suite 228 passing, was 224). No provider/API/frontend change. Restart the backend; optionally clear `backend/audio_cache/*.mp3` and `audio_assets` (the versioned hash supersedes them).
- follow_ups: If a future engine still mangles something, extend `normalize_for_speech` and bump `_SPEECH_NORM_VERSION`.

## [2026-09-13] fix — loans terminal shows loan plazos, not degenerate debt scenarios
- agent: opencode / deepseek-flash
- requirements: REQ-LM-10, REQ-LM-11 (behavior; no contract change)
- invariants: none
- files: `backend/engine/loan_offer.py`, `backend/agent/loans_fallback.py`, `backend/agent/loans.py`, `backend/tests/test_loan_offer.py`, `backend/tests/test_loans_consult.py`, `A2UI_CATALOG.md`, `backend/LOANS_CONSULT_GUIDE.md`
- decision: The loans terminal's `ScenarioComparison` was built from `engine/loans_analysis.py` debt-payoff scenarios, so a debt-free applicant (e.g. `u_don`, no `liabilities`) got cards reading "Plazo 1 meses / Interés total $0". Added `engine/loan_offer.py::term_options` (via `terms_for`) returning engine-backed plazo options 6/12/24/36/48 for the offered amount, each with monthly payment, total interest, total cost and CAT, and flagged the offered term `recommended`; `propose_offer` now returns them as `offer.options`. `agent/loans_fallback.py` builds the terminal's `ScenarioComparison` from those options (title "Opciones de plazo", `highlightIndex` = recommended) instead of the debt analysis. `agent/loans.py` instructs the model to use `options` (label "N meses") and **deterministically overwrites** any model-emitted `ScenarioComparison.scenarios` with the engine options before persistence, so correctness never depends on model adherence. The `simple` audience now gets the plazo cards in plain language (previous directive denied `ScenarioComparison`); CAT/DTI/charts/risk stay excluded for it. Debt-payoff scenarios remain in La Mesa / El Revés.
- rationale: The frontend rendered the payload faithfully, so the defect was the data: the debt analysis is meaningless for a new-loan shopper with no debt. The engine already computes per-term terms, so no client-side math and no new component were needed; `ScenarioComparison`'s `payoffMonths`/`totalInterest` map directly to a plazo and its interest. Reusing the existing component keeps the catalog ID and wire shape unchanged.
- impact: New `term_options` tests in `tests/test_loan_offer.py`; `tests/test_loans_consult.py` fallback now asserts the 5 plazo cards with positive payment/interest and the recommended term highlighted (full suite 231 passing, was 228). Prompt/guide and `A2UI_CATALOG.md` §6 updated. No invariant, provider, or API-shape change. Frontend change tracked in the frontend repo (`openspec/changes/show-loan-term-cards`).
- follow_ups: Manual verification with `u_don` (cards show 6/12/24/36/48 with real figures) and an indebted persona (La Mesa still shows debt scenarios).

## [2026-09-13] fix — recommended loan plazo is personalized, not always 24
- agent: opencode / deepseek-flash
- requirements: REQ-LM-10, REQ-LM-11 (behavior; no contract change)
- invariants: none
- files: `backend/engine/loan_offer.py`, `backend/agent/loans_fallback.py`, `backend/agent/loans.py`, `backend/tests/test_loan_offer.py`, `backend/tests/test_loans_consult.py`, `A2UI_CATALOG.md`, `backend/LOANS_CONSULT_GUIDE.md`
- decision: The plazo comparison previously flagged `months == term_months` (default 24), so the recommended card was always 24. Added a pure, deterministic `recommend_term`/`_risk_score` to `engine/loan_offer.py`: it gates plazos to those whose payment fits the affordable ceiling, scores each feasible plazo as `w_cost·norm(totalInterest) + w_burden·norm(monthlyPayment)` with `w_burden = clamp(0.25 + 0.55·risk, 0.25, 0.80)`, and picks the minimum (ties → shorter). `risk` blends income volatility, expense volatility, liquidity buffer, payment history, subscription load, tight quincena, savings-goal delay and amount-to-income. The offered term is now the recommended one, so `LoanOffer`'s term/payment/interest/CAT/schedule match the highlighted card, and a short plain-Spanish reason is attached. `term_options` takes `recommended_months`; `propose_offer` returns `options` (recommended + `reason`) and a top-level `recommendation` (`months`, `reason`, `text`, `risk`). `loans_fallback.scenario_component` adds the reason as an optional `note` on the recommended scenario, and `agent/loans.py` tells the model the recommendation/reason (backend still overwrites deterministically).
- rationale: The user requires the highlight to reflect the person (profile, chances of paying, behavior) and the requested amount, not a constant. A transparent risk-weighted trade-off between total interest and monthly burden does that while guaranteeing the recommended payment is affordable; making the offer term equal the recommendation removes the mismatch between the headline and the highlighted card.
- impact: Verified against the seeded personas: `u_don`→24 (amount vs income), `u_sofia`/`u_carmen`→36 (thin liquidity), `u_roberto`→24 (lower total interest), `u_ana` not eligible. New tests in `tests/test_loan_offer.py` (recommendation varies by profile and by requested amount; offer term == recommended term; reason present) and updated `tests/test_loans_consult.py` (full suite 234 passing, was 231). Frontend renders the optional `note` (see the frontend repo's `show-loan-term-cards` change). No invariant/API-shape change.
- follow_ups: Tune the risk weights/thresholds if the demo personas' spread needs adjusting; keep `_SPEECH_NORM_VERSION`-style versioning in mind if the option shape changes.
