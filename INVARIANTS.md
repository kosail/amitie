# INVARIANTS.md — Non-Negotiable Project Truth

> **Authority:** This file ranks above `AGENTS.md`, `SPECS.md`, and every other source of truth in this repository. If any other document, comment, or agent output conflicts with an invariant here, **this file wins**.
>
> **Change protocol:** An invariant may only change with **explicit human approval**. Every change MUST be appended to `CHANGELOG.md` with the old value, the new value, and the rationale. **Silent changes are prohibited.**
>
> These invariants are the foundation of the architecture. They are not suggestions, defaults, or preferences.

---

## A. Product invariants

- **INV-001 — Core feature.** `La Mesa + El Revés` is the core feature and the primary demo. It must never be demoted, removed, or reduced to a secondary flow.
- **INV-002 — Staged feature.** `Saving Bags` is **PENDING TO BE RELEASED** (staged, not shipped). If released, it is the secondary pillar and must never displace `La Mesa + El Revés` in scope, time, or demo priority.
- **INV-003 — Accessibility is automatic.** `Voz y Color` activates automatically from account flags (elderly, blind, other accessibility needs, or low literacy). It is not an opt-in toggle and not a separate app.
- **INV-004 — Transparency and proof are product.** `Caja de Cristal` (exposed, editable assumptions) and the `Kill Test` (the experience collapses without the LLM) are product features, not pitch-only slides.
- **INV-005 — Winning is mandatory.** Every scope, architecture, and demo decision is judged against winning the hackathon. Reliability and demonstrable impact outrank novelty for its own sake.

## B. Architecture invariants

- **INV-010 — HTTP only.** The backend communicates over plain HTTP using **REST JSON** request/response. Each response carries the full A2UI message array. **No WebSockets. No SSE. No sockets of any kind.**
- **INV-011 — Backend stack.** Backend is **Python + FastAPI**, with agent orchestration via **Google ADK**. A2UI payloads are validated with the **A2UI agent SDK**.
- **INV-012 — Provider abstraction.** Every external capability sits behind a narrow provider interface with a configured fallback chain:
  - LLM: **Gemini** (primary) → **DeepSeek** (fallback)
  - TTS: **ElevenLabs** (primary) → **edge-tts** (fallback)
  - STT: **Gemini** multimodal (primary) → **faster-whisper** (fallback)
  - Web research: **Gemini + Google Search grounding** (primary) → **deterministic price table** (fallback)
- **INV-013 — Env-only provider swap.** Switching any provider is a configuration change in `.env`. No source-code change may be required to swap a provider.
- **INV-014 — MCP is the only door.** The agent accesses all data, models, computations, and actions exclusively through MCP. There are separate in-process MCP servers: `finance`, `ui`, `voice` (`savings` is staged/pending, `INV-002`).
- **INV-015 — Deterministic math.** The LLM never computes amortization, feasibility, projections, or any other financial arithmetic. A deterministic engine does. The LLM decides strategy and which interface to build; MCP computes numbers.
- **INV-016 — A2UI is mandatory and custom.** A2UI (v0.9.1 message model) is the interface protocol. Components come only from catalogs built by this team. **No third-party UI component libraries.**
- **INV-017 — Closed loop.** Every user interaction with a generated component returns to the agent as context via the `a2ui_action` path and can change what the agent does next. The UI must never be generated once and terminate.
- **INV-018 — Traceability.** Every request carries a `trace_id`. Every LLM call and every MCP tool call emits a structured trace record (provider, model/tool, latency, tokens, error) retrievable via `/debug/trace/{trace_id}`.
- **INV-019 — Local persistence.** Persistence is a single **local SQLite** database reached only through the persistence port; there is no remote or managed database. The database file lives on the same host as the backend. Internet exposure is provided exclusively by a Cloudflare Tunnel in front of the local backend; **no application data or processing leaves the host**.

## C. Data & interface invariants

- **INV-020 — Storage.** All data lives in a local **SQLite** file accessed through the persistence port (INV-019). All data is mocked/seeded. No real banking integrations, no remote or managed database. No production/general auth system; a minimal, local, seeded **demo login** is permitted (no signup, password reset, SSO, or account lifecycle — see `SPECS.md` §12).
- **INV-021 — Persisted generation.** Every generated UI is persisted per user and associated to its domain (`loans_credits`; the `saving_bag` domain is pending, `INV-002`) and entity, stored with **placeholders** rather than literal values.
- **INV-022 — Freshness + revalidation.** Placeholders move *data* only. Before every delivery the backend hydrates placeholders from the local database (INV-019) **and** runs an agent revalidation pass that may mutate *structure*. **Stale or leaked data must never be delivered.**
- **INV-023 — Frozen frontend boundary.** The backend exposes a frozen REST contract. It has two documented surfaces: the **A2UI** contract (`SPECS.md` §8) and a plain-**REST extension** for native screens (`SPECS.md` §8.1). The frontend team owns rendering; the backend team owns data, orchestration, and logic. Backend must not depend on frontend internals.

## D. Scope & delivery invariants

- **INV-030 — Hard cut line.** The shippable scope is: two `La Mesa` mutation moments, `El Revés`, the voice-first `Loans & Credits` consult, and one accessible persona. `Saving Bags` is staged/pending (`INV-002`). Anything beyond this is cut unless it directly serves one of these.
- **INV-031 — One interaction over ten features.** Impact per engineering hour is the primary optimization. No feature ships that does not strengthen the core demonstration.
- **INV-032 — Kill Test stays truthful.** The `Kill Test` must exercise the real stored UI with frozen data and no agent. It may never be staged or faked.

## E. Security invariants

- **INV-040 — Secrets.** All credentials live only in `backend/.env`, which is git-ignored. Secrets must never be committed, logged, echoed, or embedded in code or documentation.
- **INV-041 — Rotation.** Any credential disclosed outside `.env` (for example, in a chat or planning session) is considered compromised and **must be rotated after the event**.

## F. Change-control invariants

- **INV-050 — Precedence.** `INVARIANTS.md` > `SPECS.md` > `AGENTS.md`. Conflicts resolve in that order.
- **INV-051 — Approval required.** Changing any invariant requires explicit human approval plus a `CHANGELOG.md` entry with rationale.
- **INV-052 — No silent drift.** Agents and contributors must not silently redefine, reinterpret, or work around an invariant. If an invariant appears wrong, stop, propose the change, and log it.
