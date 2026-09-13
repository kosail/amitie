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
- [x] **REQ-LOOP-05** — Every A2UI mutation endpoint returns a full A2UI message array. (The plain-REST extension in §8.1 returns domain JSON instead and is exempt from this rule and REQ-LOOP-06.)
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

## 3. Saving Bags — PENDING TO BE RELEASED

> **PENDING TO BE RELEASED.** The Saving Bags flow is staged but not part of the
> shipped surface. Its implementation is retained on disk (`engine/savings.py`,
> `mcp_servers/savings/`, `api/routers/saving_bags.py`) but is **not wired** into
> the app, the agent, or the API contract. `REQ-BAG-01..08` and `REQ-API-05` are
> deferred and not released. Do not build or depend on them.

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

- [x] **REQ-UI-01** — Generated UIs are stored per user, associated to their domain (`loans_credits`; the `saving_bag` domain is pending, §3) and entity, using placeholders.
- [x] **REQ-UI-02** — The backend hydrates placeholders with current data immediately before delivery; stale values are never delivered.
- [x] **REQ-UI-03** — A revalidation pass may mutate the stored structure; data-only changes are insufficient.
- [x] **REQ-UI-04** — Each stored UI carries a version that increments on structural change.

## 8. API contract (frozen)

- [x] **REQ-API-01** `POST /api/session`
- [x] **REQ-API-02** `POST /api/message` — `{session_id, text|audio_b64}` → `{a2ui[], surface_id, audio_ref?}`
- [x] **REQ-API-03** `POST /api/action` — `{surface_id, name, source_component_id, context}` → `{a2ui[]}`
- [x] **REQ-API-04** `GET /api/ui/{surface_id}` — hydration + revalidation → `{a2ui[]}`
- [~] **REQ-API-05** Saving bags: **PENDING TO BE RELEASED** (endpoints staged but not wired; see §3).
- [x] **REQ-API-06** `POST /api/negotiation/{session}/turn`, `POST /api/negotiation/{session}/take-control`
- [x] **REQ-API-07** `GET /api/audio/{asset_id}`
- [x] **REQ-API-08** `GET /debug/kill-test/{surface_id}`, `GET /debug/trace/{trace_id}`

- [x] **REQ-API-08b** Loans: `POST /api/loans/greeting` (personalized intro audio + session) and `POST /api/loans/consult` (`{session_id, text|audio_b64, loan_request_id?}`) both return **`multipart/form-data`** (`payload` JSON part + `audio` mp3 part; `{response_text, confidence, terminal_response}`); `GET /api/loans/{loan_request_id}` returns the hydrated terminal UI as JSON. See `LOANS_CONSULT_GUIDE.md`.
- [x] **REQ-API-08c** `POST /api/loans` — create the offered loan **only on explicit user action** (`{user_id, amount, months?, loan_request_id?}`), validated against the stored offer, inserting the `loans` row and disbursing atomically. The terminal generation never creates a loan.
- [x] **REQ-LM-10** — The loans consult returns a deterministic, engine-backed offer: backend-proposed amount (affordability), terms, IRR-based CAT, per-month schedule, and a risk panel (DTI, surplus, liquidity buffer, relative cost, income stability, payroll deduction, savings-goal delay, payment history), surfaced via a required `LoanOffer` component carrying a numeric `amount`.
- [x] **REQ-LM-11** — Audience adaptation: a deterministic classifier (`engine/audience.py`) derives `simple|standard|detailed` from age, accessibility mode, last obtained degree (`users.education_level`) and real financial activity; the loans consult and La Mesa both adapt interface complexity to its Spanish `directive`, and every persisted surface exposes it at `/audience`. `LoanOffer.amount` stays mandatory at every level.
- [x] **REQ-LM-12** — The loans consult responds within a **5 s** budget: the single LLM call is hard-capped (`LOANS_LLM_DEADLINE_SECONDS`, default 4.0) and bounded (`LOANS_MAX_TOKENS`, default 900); on timeout, provider failure, invalid output, or a low-confidence terminal the backend returns a deterministic, schema-valid terminal built from the engine (`agent/loans_fallback.py`) instead of an error. Not-eligible users (`amount <= 0`) get an explanatory `response_text` with `terminal_response = null`.
- [x] **REQ-LM-13** — Model output is normalized before validation (`ui_contract/normalize.py`): a bare action-name string becomes `{"event": {"name": ..., "context": {}}}`, and a whole `{{dot.path}}` placeholder on a numeric/boolean prop becomes a `{"path": "/dot/path"}` binding. The normalized payload is what is validated and persisted.

> **Diagnostics — not part of this frozen contract, and not for frontend use.** The frontend must not depend on `GET /debug/trace/{trace_id}`, `GET /debug/kill-test/{surface_id}`, `GET /debug/providers`, `POST /debug/stt`, or `POST /debug/tts`. They are developer tools and are disabled when `ENABLE_DEBUG_ENDPOINTS=0`.

### 8.1 Plain-REST extension (native screens, frozen)

A second, **non-A2UI** contract surface for native frontend screens that render their own UI (login, Inicio, Préstamos). These return domain JSON, not A2UI messages, and are exempt from `REQ-LOOP-05`/`REQ-LOOP-06`. All data still flows through the `finance` MCP server (`INV-014`).

- [x] **REQ-API-09** `GET /api/profile`, `GET /api/accounts`, `GET /api/liabilities` — read the seeded financial picture for a `user_id`.
- [x] **REQ-API-10** `POST /api/liabilities/{id}/payment` — internal, persisted "abono" that debits a seeded account and reduces the liability (validated atomically; never the LLM).
- [x] **REQ-API-11** `POST /api/login` — real credential verification for the two seeded personas; see `REQ-AUTH-01..04` (§12).

## 9. Data

- [x] **REQ-DATA-01** — The local SQLite schema covers: users, accounts, transactions, income_streams, subscriptions, liabilities, lender_policies, saving_bags, saving_bag_answers, saving_bag_research, saving_bag_plan, generated_ui, ui_actions, negotiation_rounds, accessibility_profiles, audio_assets, sessions, traces.
- [x] **REQ-DATA-02** — A deterministic, re-runnable seed provides: one debt persona, one accessible persona, at least six months of transaction/subscription history, and (retained but unused) one travel saving-bag record for the pending feature (§3).
- [x] **REQ-DATA-03** — Persistence is a single local SQLite database; there is no remote or managed database. All data and processing remain on the backend host.
- [x] **REQ-DATA-04** — All persistence is reached through a narrow persistence port; the agent and MCP layers never touch the SQLite driver directly.
- [ ] **REQ-DATA-05** — The local backend is exposed to the internet exclusively through a Cloudflare Tunnel; no Cloudflare database or Workers runtime is used.

> **Contract note (2026-09-12):** the plain-REST finance endpoints are now formally part of the frozen contract in §8.1 (`REQ-API-09`/`REQ-API-10`), reached only through the `finance` MCP server (`INV-014`).

## 10. Non-functional

- [x] **REQ-NFR-01** — Provider failover works without code changes and keeps development/demo alive on quota exhaustion (Gemini→DeepSeek, ElevenLabs→edge-tts, Gemini STT→faster-whisper, grounding→fallback table).
- [x] **REQ-NFR-02** — Every request and every LLM/MCP call is traceable by `trace_id`.
- [x] **REQ-NFR-03** — Modules can be built, run, and tested independently (isolated MCP servers; pure engine and hydration modules).
- [x] **REQ-NFR-04** — The demo runs on locally seeded data; when all LLM providers are unavailable the API returns a clear, retryable error (`error_code`, `retryable`) instead of a stale surface, so the system's real-time generation is always observable.
- [x] **REQ-NFR-05** — The golden path completes in approximately 90 seconds.
- [ ] **REQ-NFR-06** — The backend is reachable over the internet through a Cloudflare Tunnel while all execution and data remain local.

## 11. Demo

- [ ] **REQ-DEMO-01** — The demo shows, in order: intent → MCP retrieval → generated UI → user interaction → returned context → BreakAlert mutation → repair/reflow → El Revés negotiation → accepted outcome.
- [~] **REQ-DEMO-02** — A Saving Bag flow demonstrates a vague goal becoming a researched, dated, funded plan. **PENDING TO BE RELEASED** (§3).
- [ ] **REQ-DEMO-03** — The accessible persona demonstrates the same agent producing a different catalog with audio in/out.
- [ ] **REQ-DEMO-04** — A recorded golden-path video exists as a fallback.

## 12. Real login (native screen extension)

Added 2026-09-12, alongside the §9 finance contract note, for the native login screen. Not part of the original §8 A2UI contract.

- [x] **REQ-AUTH-01** — `POST /api/login` verifies a username + password against the `users` table (`username`, `password_hash`, `password_salt` columns) and returns `{session_id, user_id, username, accessibility_mode}` on success.
- [x] **REQ-AUTH-02** — Passwords are never stored or logged in plaintext; hashing is PBKDF2-HMAC-SHA256 with a random per-user salt (`backend/auth/passwords.py`), stdlib-only (no new dependency).
- [x] **REQ-AUTH-03** — An unknown username or an incorrect password both return `401` with the same generic message (no username enumeration).
- [x] **REQ-AUTH-04** — The seeded personas (`u_ana`, `u_don`, `u_sofia`, `u_carmen`, `u_roberto`) each get a real, fixed demo login (`demo`, `accesible`, `sofia`, `carmen`, `roberto`; password `demo1234` for all) via deterministic, fixed-salt seed hashes (`db/seed.py`) so `python -m db.init` stays reproducible (REQ-DATA-02). The five profiles span the three audience levels (`detailed`/`standard`/`simple`) and both catalogs (standard and voz-color) to showcase different generated UIs (REQ-LM-11).

## 13. Real transfers (native screen extension)

Added 2026-09-12, alongside the §9 finance contract note and §12, for the native
Transferencias screen (`hackmtyfront/openspec/changes/redesign-transfers-real-data`).
Not part of the original §8 A2UI contract; follows the exact `finance` MCP +
plain-REST pattern already established by `POST /api/liabilities/{id}/payment`.

- [x] **REQ-XFER-01** — `GET /api/recipients?user_id=` returns the user's saved
  transfer recipients: `{ recipients: [{ id, alias, clabe, bankName, createdAt }] }`,
  persisted in the new `saved_recipients` table (`backend/db/schema.sql`).
- [x] **REQ-XFER-02** — `POST /api/recipients` (`{ user_id, alias, clabe, bank_name }`)
  creates and persists a new recipient. The CLABE checksum (mod-10, weights
  3-7-1 repeating) is re-validated server-side (`mcp_servers/finance/clabe.py`)
  — the client's own validation is never trusted alone for a money-adjacent
  field. An invalid CLABE or empty alias/bank returns `{status: "error", issues: [...]}`.
- [x] **REQ-XFER-03** — `POST /api/transfers` (`{ user_id, source_account_id, amount,
  memo, destination }`, `destination` discriminated on `kind`: `{"kind": "own",
  "account_id"}` or `{"kind": "external", "clabe", "bank_name", "alias",
  "save_recipient"}`) moves real, persisted money out of `source_account_id` in
  one deterministic `database.batch()` write (`mcp_servers/finance/service.py::transfer_funds`,
  INV-015 — the LLM never computes this math):
  - `kind: "own"` validates the destination account belongs to the same user
    and differs from the source, then debits the source and credits the
    destination, recording two `transactions` rows (`category='transfer_own'`,
    one `direction='out'`, one `direction='in'`, sharing the same `memo`).
  - `kind: "external"` re-validates the CLABE checksum server-side, debits the
    source account only (no destination account exists in this system for an
    outside bank), records one `transactions` row (`category='transfer_external'`),
    and — when `save_recipient` is set — also inserts into `saved_recipients`.
  - Insufficient funds, an invalid CLABE, an unknown/foreign destination
    account, or the same account on both sides are all rejected with
    `{status: "error", issues: [...]}` (HTTP 400) and change nothing.
  - Response: `{ status, transfer, source_account, destination_account?,
    saved_recipient?, issues: [] }`, mirroring `PaymentResponse`'s status/issues
    convention so the frontend's existing `ApiError`/`issues` handling
    (`AbonoModal`) applies unchanged.
- [x] **REQ-XFER-04** — `transactions.memo` (new nullable column, idempotent
  migration in `db/schema.py::_ensure_columns`) stores the required transfer
  concept/memo for both transfer categories.

## 14. Explicitly out of scope

- Production databases or real banking integrations.
- Remote or managed databases; all persistence is a local SQLite file.
- Payment rails or real money movement with an outside bank (internal, persisted ledger movement between seeded accounts is in scope — see §9's contract note, §12, and §13).
- Deployment infrastructure, microservices orchestration, or elaborate analytics.
- Third-party UI component libraries.

> **Scope change (2026-09-12):** "Authentication / authorization systems" was removed from this list, with explicit human approval in-session. The frontend's login screen now performs real credential verification (`POST /api/login`, §12) against the two seeded personas — this stays a small, hackathon-scale mechanism (stdlib PBKDF2 password hashing, two fixed demo accounts, no signup/registration/password-reset flow), not a general auth system. See `CHANGELOG.md`.
