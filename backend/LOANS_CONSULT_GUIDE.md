# LOANS_CONSULT_GUIDE.md — Voice-first Loans & Credits consult

> **Status:** implemented. The flow is live in the backend (`/api/loans/*`,
> `agent/loans.py`). This document is the authoritative contract and the reference
> for future changes; it also records the Gemini thought-signature fix, the
> `PR_SWITCH` swap, and the loan persistence/placeholder design.
>
> **Read first:** `INVARIANTS.md` > `SPECS.md` > `A2UI_CATALOG.md` > `AGENTS.md`.
> If anything here conflicts with `INVARIANTS.md`, the invariant wins.

---

## 1. Objective

Deliver a **voice-first "new loan & credit" consult flow** that matches what the
frontend team expects, while keeping the existing La Mesa / El Revés flows
untouched.

The frontend expecting this flow:

1. Asks the backend for an opening audio that invites the user to say what they want.
2. Sends the user's answer as **text or audio**.
3. If audio, the backend transcribes it; otherwise it proceeds with the text.
4. The backend gathers the user's credit history and transactions, sends the user
   data + the bank context (`BANK_LOAN_CONTEXT.md`) + the request to the AI, and the
   AI returns a JSON response to be spoken plus a **terminal flag** and confidence.
5. The backend synthesizes an **mp3** of the response and returns it together with a
   generated UI when the interaction is terminal. The terminal UI is persisted with
   `{{placeholders}}` and re-hydrated on future fetches.

Important constraints agreed with the owner:

- **Real providers are Gemini + ElevenLabs.** A hidden env switch `PR_SWITCH=1`
  silently swaps them for DeepSeek + local Piper TTS. If `PR_SWITCH` is unset it is
  treated as `0` (real Gemini + ElevenLabs).
- **DeepSeek must be able to generate the A2UI itself** (answered in §10).
- The swap is **masked everywhere** (logs, traces, `/debug/providers`).

---

## 2. Current baseline (what exists today)

This is what the change builds on. Read the referenced files before implementing.

| Area | File(s) | Behavior today |
|---|---|---|
| Generic agent turn | `agent/service.py` | ADK tool-calling agent; **always** must call `persist_ui` or the turn errors (`"the agent did not call persist_ui"`). |
| Negotiation | `agent/negotiation.py` | Same tool-calling pattern for El Revés. |
| Providers | `providers/{gemini,deepseek,gateway,registry,voice}.py` | Gemini primary → DeepSeek fallback; ElevenLabs → edge-tts; Gemini STT → faster-whisper. |
| MCP servers | `mcp_servers/{finance,ui,voice}` | `get_financial_context`, `simulate_plan`, `persist_ui`, `hydrate_ui`, `synthesize_speech`, `transcribe_audio`, … |
| Hydration | `hydration/placeholders.py`, `hydration/service.py` | Resolves `{{path}}` placeholders, then a deterministic revalidation pass (plan / assumptions sections). |
| Contracts | `SPECS.md` §8 | `/api/message` → `{a2ui[], surface_id, audio_ref?}`. No `terminal_response`/`confidence`. |
| Catalog | `ui_contract/{catalog.json,catalog.schema.json,prompt.py}` | Flat A2UI v0.9; two catalogs (`amitie.standard.v1`, `amitie.voz-color.v1`). |
| Data | `db/schema.sql` | `generated_ui(id, user_id, domain, entity_id, catalog_id, template_json, bindings_json, version, audience, frozen_json, …)`. No loans table. |
| On disk | `backend/BANK_LOAN_CONTEXT.md` (empty), `backend/voices/*.onnx` | Bank context file to be filled; Piper voices `es_MX-claude-high`, `es_ES-sharvard-medium`. |

### Known prerequisite bug

`providers/gemini.py` does not preserve Gemini **thought signatures**. On a
tool-using turn with a Gemini 3.x model the API returns
`400 INVALID_ARGUMENT ... Function call is missing a thought_signature`, so the
`PR_SWITCH=0` (real Gemini) path fails today. **Phase 0 fixes this first** (§11).

---

## 3. Reconciliation with hard specs (what must change and why)

| Spec / contract | Conflict | Resolution |
|---|---|---|
| `SPECS.md` §8 / `REQ-API-02` | `/api/message` shape is `{a2ui[], surface_id, audio_ref?}` | **Additive dedicated endpoints** `/api/loans/*` with the new shape. Existing `/api/message` is unchanged. Add `REQ-API-09..11` to §8. |
| Agent always terminates with a UI (`agent/service.py`) | New flow needs text-only turns (`terminal_response: null`) | The new **`LoansConsultService`** is independent of the ADK agent and may return with no UI. No invariant forbids text-only turns (`INV-017` only requires the loop). |
| Audio only for accessible users (`SpeechEnricher`) | New flow wants mp3 every turn | The loans service **always** synthesizes `response_text` for the loans endpoints, regardless of accessibility. The accessible `voz-color` behavior elsewhere is unchanged. |
| `A2UI_CATALOG.md` §7 placeholders vs. agent JSON-pointer bindings | Agent emits bindings; persisted templates should use placeholders | The loans AI is instructed to emit **`{{...}}` placeholders** for important data; `persist_ui` stores the `data_model` snapshot and `hydrate_ui` resolves placeholders from it. Bindings remain valid for live sections. |
| No loan entity | "associate the UI with that loan" | Add a **`loan_requests`** table; store the terminal surface with `generated_ui.entity_id = loan_request_id`. |

> Any change to `SPECS.md`, `A2UI_CATALOG.md`, or `INVARIANTS.md` must be recorded in
> `CHANGELOG.md`.

---

## 4. Agreed behavior contract (HTTP)

All responses follow the repo's convention: HTTP 200 with a `status` field;
failures are `{status: "error", error_code, retryable, message}`.

### 4.1 Opening audio

`POST /api/loans/greeting`

Request: `{ "user_id": "u_ana" }`

Response: **`multipart/form-data`** with two parts:

- `payload` (`application/json`):
```json
{
  "status": "ok",
  "session_id": "sess_…",
  "response_text": "¿En qué te puedo ayudar hoy, Ana?",
  "audio_id": "aud_…",
  "audio_ref": "/api/audio/aud_…",
  "terminal_response": null
}
```
- `audio` (`audio/mpeg`, filename `greeting.mp3`): the spoken greeting, inline.

The greeting is personalized with the user's **first name** (`get_profile` → first
token of `name`); it falls back to a generic line when the name is missing.

### 4.2 Consult turn

`POST /api/loans/consult`

Request:
```json
{
  "session_id": "sess_…",
  "text": "quiero un crédito de 50000 para mi negocio",   // OR
  "audio_b64": "<base64>",
  "language": "es-MX",
  "loan_request_id": "loan_…"        // optional; created if absent
}
```
- If `audio_b64` is present and `text` is empty → transcribe via the `voice` MCP
  (SpeechRecognition under `PR_SWITCH`), then proceed with the transcript.
- If neither present → an error payload (still multipart, no audio part).

Response: **`multipart/form-data`** with two parts:

- `payload` (`application/json`):
```json
{
  "status": "ok",
  "loan_request_id": "loan_…",
  "response_text": "Con tus ingresos puedes acceder a…",
  "confidence": 0.87,
  "audio_id": "aud_…",
  "audio_ref": "/api/audio/aud_…",
  "terminal_response": {
    "catalog_id": "amitie.standard.v1",
    "surface_id": "surf_…",
    "a2ui": [ /* full A2UI message array */ ]
  }
}
```
- `audio` (`audio/mpeg`, filename `reply.mp3`): the spoken answer, inline.

`terminal_response` is **`null`** when the AI does not yet have enough context
(confidence ≤ 0.80 or it explicitly asks a follow-up question). If TTS is
unavailable, the `audio` part is omitted (text-only payload).

### 4.3 Re-fetch a terminal UI

`GET /api/loans/{loan_request_id}`

Returns **JSON** (no audio) with the persisted terminal surface re-hydrated
(placeholders replaced with current data), same `terminal_response` shape. 404 if
the loan request or its surface does not exist.

### 4.4 Deterministic offer + manual creation

The terminal UI **must** include `LoanOffer` (numeric `amount`, `apr`, `months`,
`monthlyPayment`, `totalInterest`, `cat`, `schedule[]`), computed by
`engine/loan_offer.py` (`propose_offer`): the backend proposes the amount from the
user's affordability and builds the risk panel (DTI, disposable surplus, liquidity
buffer, relative cost vs existing debts/`lender_policies.apr_floor`, income
stability, payroll-deduction net, savings-goal delay from retained data, and a
payment-history score projection); CAT is an IRR-based annualized cost including
fees/insurance. A `loan_offers` row is stored for the consult.

**The loan is created only when the user accepts:** `POST /api/loans`
(`{user_id, amount, months?, loan_request_id?}`) validates against the stored
offer and atomically inserts a `loans` row **and disburses** (credits checking +
a `loan_disbursement` transaction). Generation never creates a loan.

---

## 5. The AI response (structured JSON)

The consult turn is **one structured LLM call**, not an ADK tool loop.

### 5.1 Model output schema

```json
{
  "response_text": "string — the sentence(s) to speak to the user",
  "confidence": 0.0,
  "terminal_response": {
    "catalog_id": "amitie.standard.v1",
    "components": [ /* A2UI flat v0.9 components, MAY contain {{placeholders}} */ ],
    "data_model": { /* values referenced by the placeholders */ },
    "simulation": { /* optional: strategy/extra_income/… for deterministic revalidation */ }
  }
}
```
`terminal_response` may be `null`.

### 5.2 Prompt inputs

The system prompt is assembled from:

1. Role: La Mesa, voice-first loan advisor for Mexico; answer in Spanish (`es-MX`).
2. **`BANK_LOAN_CONTEXT.md`** contents (see §8). If empty, say so internally and
   fall back to a cautious generic answer.
3. The catalog description restricted to the terminal component set the mobile
   catalog implements (`agent/loans.py::_describe_allowed`) and the flat-component
   shape reminder.
4. The **output contract** above, the confidence rule, and the binding/action rules.
5. Instruction: `terminal_response = null` when more information is needed.
6. **Insight mandate (anti-generic):** must include `ScenarioComparison` with the
   offered loan's **payment-term (plazo) options** from `offer.options`
   (label "N meses", `monthlyPayment`, `payoffMonths` = months, `totalInterest`;
   highlight the selected term). The candidate plazos are **amount-banded**
   (`allowed_terms_for`: a small loan only offers short terms) and always include
   the selected term and any term the user asked for. The selected term is the
   user's requested term when they gave one (after a deterministic confirmation
   turn with its real implications — see below), otherwise `recommend_term`'s
   per-applicant pick (profile/behavior/amount, never a fixed 24). The offer's own
   `termMonths`/payment/CAT are presented at the selected plazo. The backend
   deterministically overwrites the model's scenario values with the engine
   options, so debt-payoff scenarios from `analyze_loans` are never shown in the
   loans terminal. Must also name the first credit to attack (creditor + APR),
   propose one concrete action with amount + measured effect, and mention
   subscription leak / quincena pressure when relevant. Cite the user's real
   numbers; generic advice and invented figures are forbidden.
7. **Rich-UI rule:** a terminal UI includes a payment forecast (`ForecastChart`/
   `LineChart`), a payment schedule (`PlanTable`), `BreakAlert` when the analysis
   detects a break, and key metrics (`ProgressBar`/`Badge`).
8. **Audience directive (`REQ-LM-11`):** the backend calls `get_audience(user_id)`
   and injects a deterministic `simple | standard | detailed` directive derived
   from age, accessibility, `education_level` and real activity. With `simple` the
   insight mandate shrinks (plain language, max two sections, no CAT/DTI/risk/
   `ScenarioComparison`) but `LoanOffer.amount` remains mandatory; with `detailed`
   CAT, DTI, the full risk panel and charts are required; `standard` keeps the
   current mandate. The audience object is also written to the surface data model
   at `/audience`.
9. **Shapes (`REQ-LM-13`):** `action` MUST be an object
   `{"event": {"name": ..., "context": {}}}`; numeric props MUST be a number or a
   `{"path": "/loan/..."}` binding; `{{dot.path}}` placeholders are only for text.
   `ui_contract/normalize.py` rewrites bare action strings and whole-placeholder
   numeric props before validation, so the persisted payload is always valid.

The user turn carries a **compacted** credit history (raw transactions dropped),
**plus the deterministic `Analisis`** (§6.1), **the audience object**, plus the
running conversation text.

### 5.3 Provider mechanics

- **Gemini:** pass `response_schema` (the adapter sets `response_mime_type=application/json`
  and `response_json_schema`) — provider-agnostic `LLMProvider.generate(...)`.
- **DeepSeek:** the adapter cannot enforce a JSON schema; include the schema in the
  prompt and set `response_format={"type":"json_object"}` (already the adapter's
  behavior when `response_schema` is provided).
- Parse defensively: accept raw JSON or fenced ```` ```json ````blocks. There is a
  **single** attempt bounded by `LOANS_LLM_DEADLINE_SECONDS` (and
  `LOANS_INTAKE_DEADLINE_SECONDS` for the short intake turn) plus
  `LOANS_MAX_TOKENS`; on timeout, provider failure, invalid output, or a
  low-confidence terminal, `agent/loans_fallback.py` returns a deterministic
  response. The server budget plus local TTS stays under the frontend's 12 s client
  abort. The prompt omits the long per-month `schedule` (the model binds
  `/loan/schedule`), trims the analysis payload, and caps the history to keep the
  latency down.

### 5.4 Intake phase and persisted negotiation state

The consult does **not** offer until it knows the amount (or the user explicitly
asks for the maximum). `consult` persists `requested_amount`, `purpose`, `use_max`,
`requested_term`, `term_confirmed`, `purpose_asked` in
`loan_requests.context_json` (read/written by `api/routers/loans.py`) so the
requested amount survives across turns — otherwise a later turn without an amount
would resolve to the engine maximum.

```
effective_amount = _extract_amount(text) or state.requested_amount
use_max          = state.use_max or _wants_max(text)
has_amount       = effective_amount is not None or use_max
if not has_amount:                 # intake turn
    ask naturally for the amount and/or purpose; terminal_response = null; no offer
elif requested_term and not confirmed:
    confirm the term (and ask purpose if still unknown); terminal_response = null
elif purpose unknown and not asked:
    ask the purpose once; terminal_response = null
else:
    build the offer at effective_amount and run the structured LLM turn
```

Unlike the offer, an intake turn **may** be produced by the model (a natural
question) with a deterministic fallback (`loans_fallback.intake_response`) if the
provider fails. Phrases like "el máximo" / "lo que me puedas dar" count as a
request for the engine maximum.

### 5.5 Confidence gate & persistence

```
if terminal_response is not null and confidence > 0.80:
    validate_messages(a2ui built from components)        # ui_contract.validator
    on failure: retry once with the validation issues
    on success: persist_ui(domain="loans_credits",
                           entity_id=loan_request_id,
                           catalog_id=terminal_response.catalog_id,
                           components=terminal_response.components,
                           data_model=terminal_response.data_model,
                           simulation=terminal_response.simulation)
else:
    terminal_response = null
```

`persist_ui` already validates and stores the surface; the service wraps the stored
components back into the full A2UI message array for the response.

---

## 6. Credit data

Add a finance MCP tool `get_credit_history(user_id)` (service +
`mcp_servers/finance/server.py`) returning a compact, purpose-built payload:

- Existing credit instruments (from `liabilities`): creditor, kind, balance, apr,
  minPayment, dueDay, status.
- `monthlyCashFlow` (last 6 months of income/expense aggregates) and
  `spendingByCategory` per month.
- `recentTransactions` — the most recent raw rows (`occurredOn`, `amount`,
  `direction`, `category`, `merchant`, `isSubscription`), so the model reads actual
  user behavior, not just aggregates.
- Totals (debt, minPayment) and `profile`.

Keep `get_financial_context` as the canonical A2UI data model; this tool is for the
consult prompt. Never compute financial numbers in the prompt — keep `INV-015`
(engine owns arithmetic). If the AI needs a simulated plan, it uses the existing
`simulate_plan` tool output passed as context.

### 6.1 Deterministic analysis (`analyze_loans`)

`engine/loans_analysis.py` (exposed as the `analyze_loans` MCP tool) computes, from
the user's own liabilities/transactions/subscriptions:

- **baseline** (min-payment payoff months, total interest, total paid) and the
  **avalanche vs snowball** comparison;
- **scenarios** (`ScenarioComparison` data): monthly payment, payoff months,
  total interest, interest saved and months saved for the baseline plus preset
  extra payments and a **recommended** extra (the user's surplus, or their
  subscription leak when there is no surplus). These are debt-payoff scenarios for
  the La Mesa / El Revés flows; the **loans terminal** uses the offer's `options`
  (loan payment terms) instead, shaped by `allowed_terms_for(amount)` and carrying
  the selected/requested term.

A **user-stated plazo** is extracted (`_extract_term`), stored in the loan
conversation state (`loan_requests.context_json`: `requested_term`,
`term_confirmed`) and honored. Until confirmed, the service returns a
deterministic confirmation turn (`terminal_response = null`) that states the real
implications (monthly payment, share of income, total interest, comparison to the
recommendation; if unaffordable, that it exceeds capacity) and asks to confirm;
`create_loan` then creates at that term.
- **payoffOrder** (per-creditor clear month under the chosen plan);
- **highCost** (credits ranked by APR);
- **behavior** (subscription load + share of income, expense volatility, average
  surplus, month-over-month category movers);
- **quincena** pressure (inflow/outflow/net per pay period, `tight` flag);
- **nextBestAction** (target creditor, extra amount, interest/months saved, why).

This is injected into the prompt; the model only presents it and fills
`{{placeholders}}` (e.g. `{{analysis.scenarios.1.interestSaved}}`).

---

## 7. Persistence, placeholders, hydration

- **Template:** the AI emits `{{dot.path}}` placeholders for important values, e.g.
  `{{loan.amount}}`, `{{plan.monthlyPayment}}`.
- **Snapshot:** `persist_ui` stores `data_model` in the descriptor
  (`bindings_json`) so the placeholders have a source.
- **Hydration:** `mcp_servers/ui/service.py::_render` merges the stored
  `data_model` snapshot into the context (live finance/plan values take precedence
  where they overlap), then `hydration/placeholders.py` replaces `{{...}}`; the
  deterministic revalidation pass (if `simulation` is present) recomputes plan
  sections.
- **Association:** `generated_ui.entity_id = loan_request_id`,
  `domain = "loans_credits"`.
- **Data model:** new table
  ```sql
  CREATE TABLE IF NOT EXISTS loan_requests (
      id TEXT PRIMARY KEY,
      user_id TEXT NOT NULL REFERENCES users(id),
      status TEXT NOT NULL DEFAULT 'open',   -- open | terminal | closed
      context_json TEXT NOT NULL DEFAULT '{}',
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL
  );
  ```
  Added to `db/schema.sql` (fresh `python -m db.init`).

---

## 8. `BANK_LOAN_CONTEXT.md` authoring

This file is injected verbatim into the loans system prompt. Keep it factual and
compact (it costs tokens on every turn). Suggested structure:

```markdown
# Contexto del banco — Créditos

## Productos
- Crédito personal: monto 5,000–200,000 MXN, plazo 6–48 meses, tasa 18%–36% anual.
- Crédito de nómina: …

## Elegibilidad
- Edad 18–70; antigüedad laboral ≥ 6 meses; score ≥ 600.
- Relación deuda/ingreso máxima: 40%.

## Políticas y tono
- Tono claro, cercano, sin promesas de aprobación; el banco decide tras validación.
- Siempre explicar en lenguaje simple; no inventar tasas ni montos.
- Si falta información, preguntar antes de simular.
```

Rules for the author:

- No secrets, no real PII.
- Numbers here are **context for conversation only**; any actual amortization must
  come from `engine/` via MCP tools (`INV-015`).
- The loader (`agent/bank_context.py`) reads the file from the backend root, caches
  it, and tolerates an empty file.

---

## 9. `PR_SWITCH` and local Piper TTS

### 9.1 Semantics

- `PR_SWITCH` is read by `config.py` into `Settings.pr_switch` (default `False`),
  **intentionally not documented in `.env.example`**.
- `PR_SWITCH=0` or unset → real **Gemini** (LLM/STT) + **ElevenLabs** (TTS).
- `PR_SWITCH=1` → real calls go to **DeepSeek** (LLM) and local **Piper** (
  TTS); the user-visible flow is unchanged.

### 9.2 Mapping and masking

Because the owner requires the swap to be **masked everywhere**, a thin alias
wrapper exposes the public labels while delegating to the real provider:

| Public label (reported) | Real provider under `PR_SWITCH=1` |
|---|---|
| `gemini` (primary) | DeepSeek, labeled `gemini` |
| `deepseek` (fallback) | DeepSeek |
| `elevenlabs` (primary TTS) | Piper, labeled `elevenlabs` |
| `edge_tts` (fallback TTS) | edge-tts |
| `gemini` (STT primary) | `SpeechRecognition` (Google Web Speech), labeled `gemini` |

Result: chain names read `gemini->deepseek` and `elevenlabs->edge_tts`, and
`/debug/providers`, `/debug/trace`, and logs show Gemini/ElevenLabs.

> **Warning (intentional):** masking destroys honest diagnostics. Keep it isolated
> in one wrapper so it can be disabled for debugging. Do not make decisions from
> masked traces without turning `PR_SWITCH` off.

### 9.3 PiperTTS

- New `providers/piper.py`: `PiperTTS` implementing the `TTSProvider` protocol.
- Lazy-imports `piper` (`piper-tts`); loads `voices/<voice>.onnx` (+ `.onnx.json`).
- Synthesizes 22 kHz PCM and encodes **real mp3** with `lameenc` so the endpoint
  keeps returning `audio/mpeg` (matching ElevenLabs).
- Voice selection: `Settings.piper_voice` (default `es_MX-claude-high`), directory
  `Settings.voices_dir` (default `./voices`).
- On failure, raises `ProviderUnavailableError` so the existing TTS fallback
  (`edge_tts`) engages.

New dependencies: `piper-tts`, `lameenc` (added to `requirements.txt`). `piper-tts`
pulls `onnxruntime` (large install).

---

### 9.4 Local STT: SpeechRecognition

Under `PR_SWITCH=1` the audio→text step uses the local **`SpeechRecognition`**
library (`providers/speech_recognition_stt.py`) instead of Gemini/faster-whisper.

- The backend transcribes the **audio bytes it receives**; it does **not** capture
  a microphone, so **`pyaudio` is not used** (it is only for server-side mic input).
- Engine: **Google Web Speech** (`recognize_google`). Note this is an *online*
  Google call — the library is local, the recognition is not. `STT_PROVIDER=speech_recognition`
  selects it explicitly; `SPEECH_RECOGNITION_ENGINE` (`google`|`sphinx`|`vosk`)
  and `STT_LANGUAGE` configure it (Vosk/Sphinx give fully offline options later).
- Compressed inputs (mp3) are converted to WAV with **`pydub`**, which needs the
  **`ffmpeg`** binary on the host; WAV passes through untouched.
- **`audioop-lts`** is required on Python 3.13+ (the stdlib `audioop` was removed).
- New dependencies: `SpeechRecognition`, `audioop-lts`, `pydub` (no `pyaudio`).

## 10. Can DeepSeek generate A2UI? (decision)

**Yes — no delegation to Gemini is required.** DeepSeek supports OpenAI-style
function calling, and the existing `providers/deepseek.py` already sends `tools` and
parses `tool_calls`. A2UI is plain JSON, so DeepSeek can produce the component
array. Caveats and mitigations:

- DeepSeek cannot enforce a JSON schema (`response_json_schema`); it only supports
  `response_format=json_object`. Put the schema in the prompt and validate the
  output.
- Weaker instruction/JSON adherence → always run `validate_messages` and retry once
  with the issues; if it still fails, return a text-only turn (`terminal_response=null`).
- Keep component trees modest; very large payloads are where weaker models drift.

This matters because under `PR_SWITCH=1` the UI must still be generated by the real
provider (DeepSeek).

---

## 11. Implementation plan (phases)

### Phase 0 — Gemini thought-signature prerequisite
- `providers/base.py`: add `ToolCall.thought_signature: bytes | None = None`.
- `providers/gemini.py`: capture signatures from `response.candidates[*].content.parts`
  in `_to_result`; in `_to_contents`, emit assistant `function_call` parts with
  `thought_signature = call.thought_signature or b"skip_thought_signature_validator"`.
- `agent/model.py`: preserve `part.thought_signature` in `to_llm_response` and
  `to_messages`.
- `config.py` / `.env.example`: raise `AGENT_MAX_MODEL_CALLS` default 6 → 10.
- Tests: role/signature round-trip regression.

### Phase 1 — `PR_SWITCH` + Piper
- `config.py`: hidden `pr_switch`, `piper_voice`, `voices_dir`.
- `providers/piper.py`: `PiperTTS`.
- `providers/registry.py`: swap + masking wrapper under `pr_switch`.
- `requirements.txt`: `piper-tts`, `lameenc`.
- Tests: mask on/off; Piper fallback.

### Phase 2 — Credit data + bank context
- `mcp_servers/finance/{service,server}.py`: `get_credit_history`.
- `agent/bank_context.py`: load `BANK_LOAN_CONTEXT.md` (cached, empty-safe).
- Write the `BANK_LOAN_CONTEXT.md` template (§8).

### Phase 3 — `LoansConsultService`
- `agent/loans.py`: single structured call, parse, confidence gate, validation +
  retry, `persist_ui`, audio synthesis.
- `mcp_servers/ui/service.py`: merge stored `data_model` snapshot on hydrate so
  `{{placeholders}}` resolve.

### Phase 4 — Endpoints + data
- `db/schema.sql`: `loan_requests`.
- `api/schemas.py`: `GreetingRequest/Response`, `ConsultRequest/Response`.
- `api/routers/loans.py`: greeting / consult / get.
- `api/app.py`: wire the router.
- `SPECS.md` §8: add `REQ-API-09/10/11`.

### Phase 5 — Tests, docs, guide
- Endpoint tests with fake LLM/TTS: confidence gate (persist vs text-only),
  placeholder persist→hydrate, greeting, audio on every turn.
- Update `AGENTS.md` (loans flow, `PR_SWITCH`), `A2UI_CATALOG.md` (placeholders),
  `README.md`, append `CHANGELOG.md`.

---

## 12. Testing strategy

- **Network-free by default.** Fake `LLMProvider`, `TTSProvider`, `STTProvider`;
  assert orchestration, not vendor payloads.
- **Confidence gate:** fake AI returns `confidence=0.9` + `terminal_response` →
  surface persisted; returns `confidence=0.5` → `terminal_response=null`, no surface.
- **Validation retry:** first AI response invalid → service retries → persists.
- **Placeholders:** persist a template with `{{loan.amount}}`; fetch and assert the
  value is resolved and reflects the stored snapshot.
- **`PR_SWITCH`:** with the flag on, assert runtime uses the swapped provider while
  `.name`/traces report the public label; with it off, assert Gemini/ElevenLabs.
- **Prerequisite:** Gemini `_to_contents` regression test (roles and
  `thought_signature`).

---

## 13. Risks

| Risk | Mitigation |
|---|---|
| Masking hides real failures (no honest traces) | Isolate masking in one wrapper; document that debugging requires `PR_SWITCH=0`. |
| `piper-tts`/`onnxruntime` heavy install; `lameenc` for mp3 | Optional dependency, lazy import; fallback edge-tts if unavailable. |
| Weak DeepSeek JSON adherence | Schema in prompt, `validate_messages`, one retry, then text-only. |
| Large A2UI payloads in a single structured call | Keep component trees small; validation + retry. |
| Empty `BANK_LOAN_CONTEXT.md` degrades answers | Ship the template; answer conservatively when empty. |
| Gemini thought-signature bug blocks `PR_SWITCH=0` | Phase 0 fixes it before anything else. |

---

## 14. Out of scope

- Replacing or modifying the existing `/api/message`, La Mesa, or El Revés flows.
- Real banking integrations, real money movement, auth (`INV-020`).
- Cloudflare Tunnel deployment (runbook only).

---

## 15. Definition of done

1. `/api/loans/greeting`, `/api/loans/consult`, `GET /api/loans/{id}` implemented and
   tested network-free.
2. Confidence-gated persistence with `{{placeholders}}` verified end to end.
3. `PR_SWITCH=0` uses Gemini/ElevenLabs and passes the thought-signature path;
   `PR_SWITCH=1` uses DeepSeek/Piper, masked.
4. `SPECS.md`, `AGENTS.md`, `A2UI_CATALOG.md`, `CHANGELOG.md` updated.
5. Full suite green.
