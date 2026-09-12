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
