# SPECS.md — Business Requirements

> **Authority:** `INVARIANTS.md` > this file > `AGENTS.md`.
> This is the single structured list of business requirements the project must satisfy. Each requirement is testable. IDs are stable and must be referenced by tests, commits, and `CHANGELOG.md` entries.

## Requirement status legend
`[ ]` not started · `[~]` in progress · `[x]` satisfied · `[-]` cut

---

## 1. Interaction loop (foundation)

- [x] **REQ-LOOP-01** — A user can express an intention or situation; the agent interprets it and retrieves relevant information through MCP before responding.
- [~] **REQ-LOOP-02** — The agent emits the interface as A2UI messages; the frontend renders it using the team's custom catalog. (Backend emits + validates; renderer is the frontend team's.)
- [x] **REQ-LOOP-03** — A user interaction with a generated component returns to the agent as context and can change the next decision and the next interface.
- [x] **REQ-LOOP-04** — The experience never terminates after a single generated interface; at least two structural mutations occur in a session.
- [x] **REQ-LOOP-05** — Every HTTP mutation endpoint returns a full A2UI message array.
- [x] **REQ-LOOP-06** — Every generated interface uses only components, props, and actions defined in `A2UI_CATALOG.md` for the declared catalog.

## 2. La Mesa + El Revés (CORE)

- [x] **REQ-LM-01** — On a debt-related intent, the agent retrieves liabilities, income streams, cash flow, and subscriptions through the `finance` MCP.
- [x] **REQ-LM-02** — The agent selects a restructuring strategy (reasoned by the LLM) and emits a generated strategic choice interface (tradeoff control) rather than assuming the objective.
- [x] **REQ-LM-03** — The plan is computed by the deterministic engine via `simulate_plan`; the LLM never computes amortization values.
- [x] **REQ-LM-04** — The system detects when a plan fails within the horizon (`detect_plan_breaks`) and exposes the failure month.
- [x] **REQ-LM-05** — When a plan fails, the agent emits a new, unprompted `BreakAlert` surface the user did not request. **(Mutation #1)**
- [x] **REQ-LM-06** — The agent proposes a repair, re-simulates, and re-flows the plan interface, clearing the break. **(Mutation #2)**
- [x] **REQ-LM-07** — `El Revés`: two personas (`bank` and `advocate`) negotiate over at least two rounds; each round is emitted as an A2UI update and recorded in `negotiation_rounds`.
- [x] **REQ-LM-08** — The user can seize the negotiation via a "take control" action, replacing the advocate persona with direct edits.
- [x] **REQ-LM-09** — Accepting an offer executes an MCP action and emits a final confirmed-plan interface with next steps.

## 3. Saving Bags (SECONDARY CORE)

- [x] **REQ-BAG-01** — A user can create a saving bag by name.
- [x] **REQ-BAG-02** — The agent infers a question set from the bag name and emits it as a generated A2UI form (not a fixed questionnaire).
- [x] **REQ-BAG-03** — The system researches real average costs (e.g., flights and trip costs for a travel bag) via Gemini with Google Search grounding.
- [x] **REQ-BAG-04** — Research results are cached as an immutable snapshot in `saving_bag_research`; live research runs only on create/refresh.
- [x] **REQ-BAG-05** — If grounding fails or times out, a deterministic fallback price table produces the estimate.
- [x] **REQ-BAG-06** — The agent compares the researched estimated total against the user's declared goal and surfaces the gap.
- [x] **REQ-BAG-07** — The agent computes feasibility and a projected completion date from mocked financial reality (transactions, income trends, subscriptions, liabilities).
- [x] **REQ-BAG-08** — The saving-bag UI is persisted and can be re-fetched; re-fetching reflects updated data and may mutate the interface when financial reality changes.

## 4. Voz y Color (automatic accessibility)

- [x] **REQ-ACC-01** — Account flags in `accessibility_profiles` automatically activate accessible mode (elderly, blind, other needs, low literacy).
- [x] **REQ-ACC-02** — In accessible mode the agent selects the dedicated `voz-color` catalog (high contrast, icon-first, large targets).
- [x] **REQ-ACC-03** — Every emitted surface in accessible mode includes a speech payload; audio is generated via the `voice` MCP and returned as an audio reference.
- [x] **REQ-ACC-04** — User audio input is transcribed (Gemini STT, fallback faster-whisper) and interpreted by the agent to determine the next step.
- [x] **REQ-ACC-05** — Synthesized audio is cached by text hash so repeat runs are fast and resilient.
- [x] **REQ-ACC-06** — Non-flagged users receive the standard catalog, making the adaptability visible by contrast.

## 5. Caja de Cristal (transparency)

- [x] **REQ-CC-01** — Generated financial surfaces can include a "why you are seeing this" panel that exposes the assumptions and data used.
- [x] **REQ-CC-02** — At least one assumption is editable by the user; editing it causes the agent to rebuild the outcome.

## 6. Kill Test (proof)

- [x] **REQ-KT-01** — A debug endpoint serves a persisted, hydrated UI with frozen data and no agent involvement.
- [x] **REQ-KT-02** — The Kill Test output must be the genuine stored artifact, never re-generated or staged.

## 7. UI persistence & hydration

- [x] **REQ-UI-01** — Generated UIs are stored per user, associated to `loans_credits` or `saving_bag` and their entity, using placeholders.
- [x] **REQ-UI-02** — The backend hydrates placeholders with current data immediately before delivery; stale values are never delivered.
- [x] **REQ-UI-03** — A revalidation pass may mutate the stored structure; data-only changes are insufficient.
- [x] **REQ-UI-04** — Each stored UI carries a version that increments on structural change.

## 8. API contract (frozen)

- [x] **REQ-API-01** `POST /api/session`
- [x] **REQ-API-02** `POST /api/message` — `{session_id, text|audio_b64}` → `{a2ui[], surface_id, audio_ref?}`
- [x] **REQ-API-03** `POST /api/action` — `{surface_id, name, source_component_id, context}` → `{a2ui[]}`
- [x] **REQ-API-04** `GET /api/ui/{surface_id}` — hydration + revalidation → `{a2ui[]}`
- [x] **REQ-API-05** Saving bags: `POST /api/saving-bags`, `GET /api/saving-bags[/{id}]`, `POST /api/saving-bags/{id}/answer`, `POST /api/saving-bags/{id}/refresh`
- [x] **REQ-API-06** `POST /api/negotiation/{session}/turn`, `POST /api/negotiation/{session}/take-control`
- [x] **REQ-API-07** `GET /api/audio/{asset_id}`
- [x] **REQ-API-08** `GET /debug/kill-test/{surface_id}`, `GET /debug/trace/{trace_id}`

- [x] **REQ-API-08b** Loans: `POST /api/loans/greeting` (intro audio + session), `POST /api/loans/consult` (`{session_id, text|audio_b64, loan_request_id?}` → `{response_text, confidence, terminal_response, audio_ref}`), `GET /api/loans/{loan_request_id}` (hydrated terminal UI). See `LOANS_CONSULT_GUIDE.md`.

> **Diagnostics — not part of this frozen contract, and not for frontend use.** The frontend must not depend on `GET /debug/trace/{trace_id}`, `GET /debug/kill-test/{surface_id}`, `GET /debug/providers`, `POST /debug/stt`, or `POST /debug/tts`. They are developer tools and are disabled when `ENABLE_DEBUG_ENDPOINTS=0`.

## 9. Data

- [x] **REQ-DATA-01** — The local SQLite schema covers: users, accounts, transactions, income_streams, subscriptions, liabilities, lender_policies, saving_bags, saving_bag_answers, saving_bag_research, saving_bag_plan, generated_ui, ui_actions, negotiation_rounds, accessibility_profiles, audio_assets, sessions, traces.
- [x] **REQ-DATA-02** — A deterministic, re-runnable seed provides: one debt persona, one accessible persona, one travel saving bag, and at least six months of transaction/subscription history.
- [x] **REQ-DATA-03** — Persistence is a single local SQLite database; there is no remote or managed database. All data and processing remain on the backend host.
- [x] **REQ-DATA-04** — All persistence is reached through a narrow persistence port; the agent and MCP layers never touch the SQLite driver directly.
- [ ] **REQ-DATA-05** — The local backend is exposed to the internet exclusively through a Cloudflare Tunnel; no Cloudflare database or Workers runtime is used.

> **Contract note (2026-09-12):** `backend/api/routers/finance.py` adds `GET /api/profile`, `GET /api/accounts`, `GET /api/liabilities`, and `POST /api/liabilities/{id}/payment` alongside this section's A2UI-only contract, for native frontend screens (Inicio, Préstamos) that render their own UI instead of a generated surface. Still reached only through the `finance` MCP server (INV-014). Not yet promoted to numbered `REQ-API-*` entries — pending an explicit decision on whether to formalize this as a second, non-A2UI contract surface. See `CHANGELOG.md`.

## 10. Non-functional

- [x] **REQ-NFR-01** — Provider failover works without code changes and keeps development/demo alive on quota exhaustion (Gemini→DeepSeek, ElevenLabs→edge-tts, Gemini STT→faster-whisper, grounding→fallback table).
- [x] **REQ-NFR-02** — Every request and every LLM/MCP call is traceable by `trace_id`.
- [x] **REQ-NFR-03** — Modules can be built, run, and tested independently (isolated MCP servers; pure engine and hydration modules).
- [x] **REQ-NFR-04** — The demo runs on locally seeded data; when all LLM providers are unavailable the API returns a clear, retryable error (`error_code`, `retryable`) instead of a stale surface, so the system's real-time generation is always observable.
- [x] **REQ-NFR-05** — The golden path completes in approximately 90 seconds.
- [ ] **REQ-NFR-06** — The backend is reachable over the internet through a Cloudflare Tunnel while all execution and data remain local.

## 11. Demo

- [ ] **REQ-DEMO-01** — The demo shows, in order: intent → MCP retrieval → generated UI → user interaction → returned context → BreakAlert mutation → repair/reflow → El Revés negotiation → accepted outcome.
- [ ] **REQ-DEMO-02** — A Saving Bag flow demonstrates a vague goal becoming a researched, dated, funded plan.
- [ ] **REQ-DEMO-03** — The accessible persona demonstrates the same agent producing a different catalog with audio in/out.
- [ ] **REQ-DEMO-04** — A recorded golden-path video exists as a fallback.

## 12. Real login (native screen extension)

Added 2026-09-12, alongside the §9 finance contract note, for the native login screen. Not part of the original §8 A2UI contract.

- [x] **REQ-AUTH-01** — `POST /api/login` verifies a username + password against the `users` table (`username`, `password_hash`, `password_salt` columns) and returns `{session_id, user_id, username, accessibility_mode}` on success.
- [x] **REQ-AUTH-02** — Passwords are never stored or logged in plaintext; hashing is PBKDF2-HMAC-SHA256 with a random per-user salt (`backend/auth/passwords.py`), stdlib-only (no new dependency).
- [x] **REQ-AUTH-03** — An unknown username or an incorrect password both return `401` with the same generic message (no username enumeration).
- [x] **REQ-AUTH-04** — The two seeded personas (`u_ana`/`u_don`) each get a real, fixed demo login (`demo`/`demo1234` and `accesible`/`demo1234`) via deterministic, fixed-salt seed hashes (`db/seed.py`) so `python -m db.init` stays reproducible (REQ-DATA-02).

## 13. Explicitly out of scope

- Production databases or real banking integrations.
- Remote or managed databases; all persistence is a local SQLite file.
- Payment rails or real money movement with an outside bank (internal, persisted ledger movement between seeded accounts is in scope — see §9's contract note and §12).
- Deployment infrastructure, microservices orchestration, or elaborate analytics.
- Third-party UI component libraries.

> **Scope change (2026-09-12):** "Authentication / authorization systems" was removed from this list, with explicit human approval in-session. The frontend's login screen now performs real credential verification (`POST /api/login`, §12) against the two seeded personas — this stays a small, hackathon-scale mechanism (stdlib PBKDF2 password hashing, two fixed demo accounts, no signup/registration/password-reset flow), not a general auth system. See `CHANGELOG.md`.
