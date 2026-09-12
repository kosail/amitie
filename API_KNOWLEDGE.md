# API_KNOWLEDGE.md — Frontend AI Contract Manual

> **Audience: the React frontend AI agent. Not for humans.**
> This is the authoritative, self-contained contract for talking to the La Mesa
> backend. Read it fully before writing any client code.
>
> **LANGUAGE RULE (non-negotiable):** this document is in English, but **every
> string the app shows or speaks to the user MUST be in Spanish (`es-MX`)**.
> Backend-provided text (`assistant_text`, `response_text`, component labels,
> `message`, `issues`) is **already Spanish** — render it **verbatim**. Never
> translate, paraphrase, or rewrite it. Only strings the frontend authors itself
> (screen titles, button chrome, static error copy) must be written in Spanish.

Base URL: `http://127.0.0.1:8000` (or the Cloudflare Tunnel URL provided at demo
time). All requests/responses are JSON unless stated otherwise. Money is MXN.

---

## 0. Golden rules (read first)

1. **A2UI is rendered, not interpreted.** Every `a2ui` field is a JSON array of
   A2UI messages. Apply them in order to build/update a surface tree. Never
   re-implement the UI in React components outside the catalog.
2. **Only catalog components exist.** Render exactly the component types in §4.
   Unknown types must be skipped safely (log them), never crash.
3. **All UI text is Spanish.** See the language rule above.
4. **The interaction never ends after one screen.** Send a message or action →
   render the returned surface → user interacts → send the new action. Loop.
5. **Errors are handled, not fatal.** HTTP 200 with `status:"error"` is a normal
   handled error. Show a Spanish error state; if `retryable` is true, offer retry.
6. **Never trust stale UI.** After a mutation, the *authoritative* surface is
   `GET /api/ui/{surface_id}` (hydration + revalidation). See §5.
7. Every response carries an `x-trace-id` header. Log it; it is the support handle.

---

## 1. Response envelope & errors

Most agent responses share this shape (`AgentResponse`):

```jsonc
{
  "status": "ok" | "error",
  "surface_id": "surf_…",              // null when the turn produced no surface
  "a2ui": [ /* A2UI messages */ ],      // full message array (REQ-LOOP-05)
  "assistant_text": "texto en español",
  "issues": ["…"],                      // validation issues (may be [])
  "message": null,                      // human-readable error, Spanish
  "actor": null,                        // negotiation only: "bank" | "advocate"
  "round": null,                        // negotiation only
  "catalog_id": "amitie.standard.v1",
  "audio_ref": "/api/audio/aud_…",      // present when speech was generated
  "error_code": null,                   // see table below
  "retryable": false
}
```

### Error codes

| `error_code` | Meaning | Frontend behavior (Spanish UX) |
|---|---|---|
| `provider_unavailable` | All LLM providers failed | "No pudimos generar la respuesta. Intenta de nuevo." + retry button |
| `model_call_limit` | Agent exceeded its call budget | Same as above |
| `agent_error` | The agent could not produce a UI / invalid output | "Algo salió mal. Intenta de nuevo." + retry |
| `transcription_failed` | Audio → text failed | "No pudimos entender el audio. Intenta de nuevo o escribe." |
| `bad_request` | Missing text/audio or invalid input | Do not retry; validate input |
| `200 + status:"error"` | Generic handled error | Use `message` verbatim |

### HTTP status codes

| Code | When |
|---|---|
| 200 | Normal success **and** handled agent errors (`status:"error"`) |
| 401 | `POST /api/login` wrong credentials (body `{"detail":"Usuario o contraseña incorrectos."}`) |
| 404 | Unknown `session_id`, `surface_id`, `loan_request_id`, or audio asset |
| 400 | `POST /api/liabilities/{id}/payment` rejected (insufficient funds, inactive debt); `POST /api/loans` rejected (invalid or above the offered amount) |

---

## 2. Auth & session

### `POST /api/login`

Request: `{ "username": "demo", "password": "demo1234" }`

Response 200 (`LoginResponse`):
```json
{ "session_id": "sess_…", "user_id": "u_ana", "username": "demo", "accessibility_mode": null }
```
Response 401: `{ "detail": "Usuario o contraseña incorrectos." }`

**Seeded demo credentials (use these):**

| username | password | user_id | name | accessibility_mode |
|---|---|---|---|---|
| `demo` | `demo1234` | `u_ana` | Ana López | `null` (standard) |
| `accesible` | `demo1234` | `u_don` | Don Miguel | `low_literacy` (accessible) |

`accessibility_mode != null` → the backend will emit the `amitie.voz-color.v1`
catalog and attach speech automatically. Do not add a toggle.

### `POST /api/session` (no-auth alternative)

Request: `{ "user_id": "u_ana" }` → `{ "session_id": "sess_…", "user_id": "u_ana" }`.
Prefer `/api/login` for the login screen; `/api/session` is for flows that start
without credentials.

Store `session_id`; send it on `POST /api/message` and loans.

---

## 3. A2UI rendering contract (core)

Every `a2ui` is a JSON array; each message carries `"version": "v0.9"`.

| Message | Body | Meaning |
|---|---|---|
| `createSurface` | `{ surfaceId, catalogId }` | Create the root surface; `catalogId` selects styling |
| `updateComponents` | `{ surfaceId, components: [...] }` | Upsert components (flit list; `root` is the tree root) |
| `updateDataModel` | `{ surfaceId, path, value }` | Merge/replace data at a JSON Pointer path |
| `deleteSurface` | `{ surfaceId }` | Remove the surface |

**Component shape (flat v0.9):** `{ "id": "root", "component": "Column", "children": ["a","b"], "gap": 12 }`
— the type is a **string**, props are **siblings**. Never use the v0.8 nested form.

**Apply order** for a message array: `createSurface` → `updateComponents` →
`updateDataModel`. Build a map `id -> component`, find `root`, render recursively.

### Data binding

Any prop may be a literal or a binding `{ "path": "/json/pointer" }`. Resolve
bindings against the surface **data model** (the value from `updateDataModel`).
Root keys are flat (no `/finance` wrapper):
`profile, liabilities, totals, incomeStreams, subscriptions, subscriptionTotal, cashFlow, plan, speech`.

Example: `{"path": "/plan/months"}` → `dataModel.plan.months`.

### Catalogs

| `catalogId` | Meaning |
|---|---|
| `amitie.standard.v1` | Default |
| `amitie.voz-color.v1` | Accessible: high contrast, icon-first, large targets, TTS-first. Same components, different styling. Automatic. |

### Actions (user → backend)

Interactive components carry `action`:
```json
{ "action": { "event": { "name": "tune_tradeoff", "context": { "value": "/ui/strategyTilt" } } } }
```
When the user interacts, send `POST /api/action` (§5). **Resolve any binding
values in `context` against the current data model before sending** (the backend
expects literal values). Map: `name` = `event.name`, `source_component_id` =
component `id`, `context` = resolved `event.context`.

Defined action names: `select_strategy`, `tune_tradeoff`, `request_simulation`,
`approve_plan`, `toggle_assumption`, `take_control`, `accept_offer`, `request_loan`.

> **Routing exception:** `request_loan` (emitted by `LoanOffer`) is **client-routed**:
> do **NOT** send it to `POST /api/action`. When the user accepts, call
> `POST /api/loans` directly (§6). Every other action name goes to `POST /api/action`.

### Speech (accessible / audio surfaces)

- Accessible surfaces include a `/speech` object in the data model:
  `{ "text": "…", "audioRef": "/api/audio/aud_…", "provider": "…" }`.
- Responses also expose a top-level `audio_ref`. Fetch it with `GET /api/audio/{id}`
  and play the `audio/mpeg`.
- **Auto-play policy:** when `catalog_id == "amitie.voz-color.v1"` or an
  `audio_ref` is present, play the audio (after the first user gesture, if the
  browser requires it). Keep a visible "replay" affordance.

---

## 4. Component & action reference

Render only these. `req` = required props. Any prop may be a binding.

| Component | req | props |
|---|---|---|
| `Column` | children | children(idArray), gap, align, justify |
| `Row` | children | children(idArray), gap, align, justify |
| `Card` | – | children(idArray), title, tone(neutral/positive/warning/danger) |
| `Text` | text | text(dynamicString), variant(body/muted/caption), tone |
| `Heading` | text | text, level(1/2/3) |
| `Divider` | – | – |
| `Badge` | label | label, tone(neutral/positive/warning/danger) |
| `Button` | label, action | label, variant(primary/secondary/ghost/danger), action |
| `ChoiceGroup` | options, action | options[{value,label,description?}], value, multiple, action |
| `Slider` | min, max, action | min, max, step, value, label, action |
| `TextField` | label, action | label, value, placeholder, action |
| `DebtNode` | creditor, balance, apr, minPayment | creditor, balance, apr, minPayment, kind, badge |
| `TradeoffScale` | leftLabel, rightLabel, action | leftLabel, rightLabel, value(0–100), action |
| `BreakAlert` | month, shortfall | month, shortfall, reasons[], assumptions[] |
| `PlanTable` | months | months[{month,totalBalance,payment,interest,cash}], breakMonth |
| `OfferCard` | actor, headline, terms | actor(bank/advocate), headline, terms{apr,months,monthlyPayment,totalCost}, action |
| `NegotiationTranscript` | rounds | rounds[{round,actor,summary}] |
| `List` | children | children(idArray), ordered |
| `ProgressBar` | value | value, max, label |
| `AssumptionChip` | label, value | label, value, editable, path, action |
| `LineChart` | points | points[{label,value}], title, yLabel |
| `BarChart` | bars | bars[{label,value}], title |
| `ForecastChart` | forecast | forecast[{period,value}], actual, title |
| `ScenarioComparison` | scenarios | scenarios[{label,monthlyPayment,payoffMonths,totalInterest,interestSaved,monthsSaved}], highlightIndex, title |
| `LoanOffer` | amount, apr, months, monthlyPayment, totalInterest, cat | amount(number\|binding), apr, months, monthlyPayment, totalInterest, cat, totalCost, schedule[{month,payment,interest,principal,balance}], action |

**Rendering notes:** `Column.children`/`Row.children`/`Card.children`/`List.children`
are arrays of component ids present in the same `updateComponents`. `OfferCard`'s
`action` is `accept_offer`. `TextField`/`ChoiceGroup`/`Slider` submit via their action.

---

## 5. Chat / La Mesa agent loop

### `POST /api/message`

Request:
```json
{ "session_id": "sess_…", "text": "Tengo 5 deudas y ya no puedo", "language": "es-MX" }
```
or audio:
```json
{ "session_id": "sess_…", "audio_b64": "<base64>", "language": "es-MX" }
```
(`audio_b64` is transcribed server-side then treated as `text`.)

Response: `AgentResponse` (§1). Render `a2ui`.

### `POST /api/action`

```json
{ "surface_id": "surf_…", "name": "approve_plan", "source_component_id": "plan", "context": { "extra_income": 8000 } }
```
Response: `AgentResponse`. `name:"accept_offer"` is special (finishes El Revés; §7).

### `GET /api/ui/{surface_id}`

Returns `UiResponse`:
```json
{ "status":"ok", "surface_id":"surf_…", "a2ui":[…], "issues":[], "catalog_id":"…", "audio_ref":null }
```
404 if unknown. **This is the hydrated, revalidated surface** (fresh values;
structure may have changed, e.g. a `BreakAlert` inserted/removed). Prefer this
for the final render after a mutation.

### Interaction state machine

```
login → message(text|audio) → render(a2ui) → GET /api/ui/{surface_id} (refresh)
  → user interacts with a component (action) → POST /api/action → render(a2ui) → …
```
Show `assistant_text` as the agent's chat bubble (Spanish, verbatim). If
`status:"error"`, show the Spanish error and offer retry when `retryable`.

Typical La Mesa debt flow (backend-driven, do not script it yourself):
intent → retrieval → surface (DebtNode/TradeoffScale) → tradeoff → **BreakAlert**
(mutation #1, unrequested) → repair → plan without alert (mutation #2) → El Revés.

---

## 6. Loans & Credits consult (multipart)

`greeting` and `consult` return **`multipart/form-data`** (not JSON):

- part `payload` (`application/json`): the JSON object below.
- part `audio` (`audio/mpeg`, filename `greeting.mp3`/`reply.mp3`): the spoken mp3 **inline**.

Parse both; there is no `audio_ref`-only response here (an `audio_ref` field is
still included for reuse). If TTS was unavailable, the `audio` part is omitted.

### `POST /api/loans/greeting`

Request: `{ "user_id": "u_ana" }`

`payload`:
```json
{ "status":"ok", "session_id":"sess_…", "response_text":"¿En qué te puedo ayudar hoy, Ana?",
  "audio_id":"aud_…", "audio_ref":"/api/audio/aud_…", "terminal_response":null }
```
Play the `audio` part; show `response_text` (Spanish). Store `session_id`.

### `POST /api/loans/consult`

Request:
```json
{ "session_id":"sess_…", "text":"quiero un crédito de 50000", "language":"es-MX", "loan_request_id":null }
```
or `"audio_b64":"<base64>"` instead of `text`.
`loan_request_id`: omit on the first turn (backend creates one), then reuse it.

`payload`:
```json
{ "status":"ok", "loan_request_id":"loan_…", "response_text":"…", "confidence":0.87,
  "audio_id":"aud_…", "audio_ref":"/api/audio/aud_…",
  "terminal_response": { "catalog_id":"amitie.standard.v1", "surface_id":"surf_…", "a2ui":[…] } }
```

**Decision rule (critical):**
- `terminal_response == null` → **not finished**. Play/display `response_text`,
  keep the mic/input open, and send the user's next `consult` (same
  `loan_request_id`). This is the conversational intake (the model asked a follow-up).
- `terminal_response != null` → **interaction ended**. Render `terminal_response.a2ui`
  (structure + bindings; charts/`ScenarioComparison`), play the audio. The UI is
  persisted and associated with `loan_request_id`.

### `GET /api/loans/{loan_request_id}`

Returns **JSON** `LoansConsultResponse` with the hydrated terminal UI
(`terminal_response`, `audio_ref`), for re-fetching a finished consult.

**Value rule:** the terminal UI is engine-backed and user-specific (scenarios,
interest saved, payoff order, next-best action, loan offer). Render it verbatim;
do not add numbers of your own.

**LoanOffer (always present in a terminal consult).** The terminal `a2ui` contains
a `LoanOffer` component with the bank's deterministic offer: `amount`, `apr`,
`months`, `monthlyPayment`, `totalInterest`, `cat`, `totalCost`, and
`schedule[{month,payment,interest,principal,balance}]`. The backend proposes the
**amount** from the user's affordability; `warnings[]` explain any risk (DTI,
liquidity buffer, relative cost, income stability, savings-goal delay, payment
history). Its action is `request_loan`.
- **Extract the amount:** `LoanOffer.amount` is a number (the backend resolves
  `/loan/*` bindings), or read `updateDataModel.value.loan.amount`. Full terms at
  `/loan`.
- **`cat` is approximate:** it is an IRR-based annualized cost including fees and
  insurance, **not** the official Banxico CAT — label it "CAT (aproximado)".
- **Do not create the loan on render.** Only when the user explicitly accepts,
  call `POST /api/loans`.

**Risk panel** — read it from `updateDataModel.value.loan.risk` (and top-level
`.../loan/warnings: string[]`) to show *why* the offer is what it is (display only;
never recompute):
```jsonc
{
  "dti":                    { "existing": 0.0, "withOffer": 0.0, "cap": 0.35, "flag": false },
  "surplus":                { "monthly": 0.0, "discretionarySpend": 0.0, "subscriptions": 0.0, "minPayment": 0.0 },
  "liquidityBufferMonths":  0.0,
  "relativeCost":           { "offeredApr": 0.24, "worstExistingApr": 0.0, "aprFloor": 0.0, "worse": false },
  "incomeStability":        { "coefficientOfVariation": 0.0, "flag": false },
  "payrollDeduction":       { "applied": false, "netPerPeriod": null },  // applied is currently always false
  "savingsImpact":          { "goal": "…", "monthsBefore": 0, "monthsAfter": 0, "delayedMonths": 0 }, // or null
  "paymentHistory":         { "available": true, "onTimeRatio": 0.8, "late": 1, "missed": 0, "projectedScoreDelta": 2 }
}
```

**Not affordable / amount = 0.** If the user cannot afford any amount, the engine
proposes `amount = 0`; the server then cannot produce a valid `LoanOffer`, so
`terminal_response` stays `null` and the turn remains conversational. In that case
show `response_text` and do **not** render an offer.

**Two distinct ids:** `loan_request_id` is the **consult** record (auto-created on
the first `consult`); the `loans.id` returned by `POST /api/loans` is the **actual
credit** created only on acceptance.

### `POST /api/loans` — create the loan (manual, user decision)

Request:
```json
{ "user_id":"u_don", "amount":47500, "months":0, "loan_request_id":"loan_…" }
```
`amount` must not exceed the offered amount; `months`/APR default to the bank
product. Response (`LoanResponse`):
```json
{ "status":"ok", "loan": { "id":"loan_…", "amount":47500, "apr":0.24, "termMonths":24,
  "monthlyPayment":2520.1, "totalInterest":…, "cat":…, "schedule":[…] } }
```
`400` if invalid or above the offer. The backend inserts the loan **and disburses**
it (credits the checking account + records a `loan_disbursement` transaction)
atomically. **Never call this until the user confirms.**

---

## 7. El Revés negotiation

### `POST /api/negotiation/{session_id}/turn`

Request: `{ "user_id": "u_ana", "position": {} }`

Response `AgentResponse` with `actor` (`"bank"`/`"advocate"`) and `round`.
Render `OfferCard` + `NegotiationTranscript`. Call repeatedly to advance rounds.

### `POST /api/negotiation/{session_id}/take-control`

Request: `{ "user_id": "u_ana", "position": { "monthlyPayment": 3500 } }`
The user seizes the negotiation; the advocate is replaced by their position.

### Accept an offer

Send `POST /api/action` with `name:"accept_offer"` and
`context:{ "session_id": "sess_…", "offer": {……} }` (the offer object from the
`OfferCard`/response). The response contains the final confirmed plan (`PlanTable`).

Max 3 rounds; on the 4th the backend returns a handled error.

---

## 8. Saving Bags — PENDING TO BE RELEASED

> **Do not implement.** The Saving Bags flow is staged but **not released**; its
> endpoints (`/api/saving-bags*`) are **not registered** and the agent does not
> offer it. Ignore any historical references. This section is intentionally empty.

---

## 9. Native REST reads/writes (non-A2UI screens)

Plain JSON for screens that render their own UI (Inicio, Préstamos, login).
`user_id` defaults to `u_ana`.

| Method/path | Request | Response |
|---|---|---|
| `GET /api/profile?user_id=` | – | `{ profile: {id,name,age,city,monthlyIncome,payFrequency,creditScore,accessibilityMode} }` (404 unknown) |
| `GET /api/accounts?user_id=` | – | `{ accounts: [{id,kind,institution,balance,currency}] }` |
| `GET /api/liabilities?user_id=` | – | `{ liabilities:[{id,creditor,kind,principal,balance,apr,minPayment,dueDay,nominaDiscount,status}], total_debt, total_min_payment }` |
| `POST /api/liabilities/{id}/payment` | `{ user_id, amount, account_id? }` | `{ status, applied_amount, liability, account, transaction, issues }`; **400** if rejected |

Payment is atomic and deterministic; 400 on inactive debt or insufficient funds.
Never compute interest client-side.

---

## 10. Audio

`GET /api/audio/{asset_id}` → binary `audio/mpeg` (404 if unknown). Use it for
`audio_ref`/`/speech.audioRef`; cache with the provided `Cache-Control`.
Loans return audio inline (multipart); accessible surfaces reference it.

---

## 11. Diagnostics appendix — **DO NOT USE IN THE PRODUCT UI**

These are developer tools under `/debug/*`; they may be removed at runtime when
`ENABLE_DEBUG_ENDPOINTS=0`. The frontend must never call them in normal flows.

| Method/path | Use |
|---|---|
| `GET /debug/providers` | Probe LLM/research/TTS health |
| `POST /debug/stt` | Transcribe a base64 clip (isolated) |
| `POST /debug/tts` | Synthesize text to mp3 (`?raw=true` streams bytes) |
| `GET /debug/trace/{trace_id}` | Inspect a request's events |
| `GET /debug/kill-test/{surface_id}` | Serve a frozen stored surface |

`GET /healthz` → `{ "status": "ok" }` (safe to poll).

---

## 12. Spanish UX rules

- Every label, placeholder, toast, empty state, and error the frontend authors
  **must be Spanish**. Suggested strings:
  - Provider error: "No pudimos generar la respuesta. Intenta de nuevo."
  - Retry button: "Reintentar".
  - Mic: "Hablar", "Escuchando…", "Enviar audio".
  - Loading: "Un momento…".
- Backend text is Spanish; render **verbatim**. Do not translate or shorten it.
- Speech synthesis language is `es-MX`; request audio with `language:"es-MX"`.

---

## 13. Playbooks (exact sequences)

**A. Debt → El Revés (u_ana)**
1. `POST /api/login {demo, demo1234}` → `session_id`.
2. `POST /api/message {session_id, text:"Tengo 5 deudas y ya no puedo"}` → render `a2ui`.
3. `GET /api/ui/{surface_id}` → refreshed surface (`BreakAlert` may appear).
4. User adjusts (`tune_tradeoff`) → `POST /api/action` → render.
5. User approves/repairs (`approve_plan`, context `{extra_income}`) → render (alert clears).
6. `POST /api/negotiation/{session_id}/turn` (bank) → render `OfferCard`+`NegotiationTranscript`.
7. `POST /api/negotiation/{session_id}/turn` (advocate) → render.
8. Optional `POST /api/negotiation/{session_id}/take-control`.
9. `POST /api/action {name:"accept_offer", context:{session_id, offer}}` → final `PlanTable`.

**B. Loans (u_ana → u_don for affordability)**
1. `POST /api/loans/greeting {user_id}` → parse multipart; play audio; store `session_id`.
2. `POST /api/loans/consult {session_id, text|audio_b64}` → parse multipart.
3. If `terminal_response == null`: play/display `response_text`; go to step 2 with the user's reply and the returned `loan_request_id`.
4. Else render `terminal_response.a2ui` (includes `LoanOffer` with numeric `amount` + `schedule`). Read the amount from `LoanOffer.amount` or `updateDataModel.value.loan.amount`.
5. If the user accepts, `POST /api/loans {user_id, amount, loan_request_id}` → loan created + disbursed. If they decline, do nothing.

**C. Accessible (u_don)**
1. `POST /api/login {accesible, demo1234}` → `accessibility_mode:"low_literacy"`.
2. Any surface uses `catalog_id:"amitie.voz-color.v1"` and includes `/speech`; render with accessible styling and auto-play `audio_ref`.

**D. Saving Bags — PENDING TO BE RELEASED.**
Do not implement; the endpoints and agent flow are not released (§8).

---

## 14. TypeScript appendix

```ts
// ---- envelopes ----
type Status = "ok" | "error";

interface AgentResponse {
  status: Status;
  surface_id: string | null;
  a2ui: A2uiMessage[];
  assistant_text: string;
  issues: string[];
  message: string | null;
  actor: "bank" | "advocate" | null;
  round: number | null;
  catalog_id: string | null;
  audio_ref: string | null;
  error_code: string | null;
  retryable: boolean;
}

interface UiResponse { status: Status; surface_id: string; a2ui: A2uiMessage[]; issues: string[]; catalog_id: string | null; audio_ref: string | null; }

interface LoginResponse { session_id: string; user_id: string; username: string; accessibility_mode: string | null; }
interface SessionResponse { session_id: string; user_id: string; }

// Saving Bags: PENDING TO BE RELEASED — no types exposed.

// ---- A2UI ----
type A2uiMessage =
  | { version: "v0.9"; createSurface: { surfaceId: string; catalogId: string } }
  | { version: "v0.9"; updateComponents: { surfaceId: string; components: A2uiComponent[] } }
  | { version: "v0.9"; updateDataModel: { surfaceId: string; path: string; value: unknown } }
  | { version: "v0.9"; deleteSurface: { surfaceId: string } };

interface A2uiComponent { id: string; component: string; [prop: string]: unknown; }
type A2uiBinding = { path: string };

interface A2uiAction { action: { event: { name: string; context: Record<string, unknown> } } }

// ---- loans (multipart payload part) ----
interface LoansGreetingPayload { status: Status; session_id: string; response_text: string; audio_id: string | null; audio_ref: string | null; terminal_response: null; }
interface LoansConsultPayload {
  status: Status; loan_request_id: string; response_text: string; confidence: number;
  audio_id: string | null; audio_ref: string | null;
  terminal_response: { catalog_id: string; surface_id: string; a2ui: A2uiMessage[] } | null;
}
// LoanOffer is inside terminal_response.a2ui; the amount is always extractable.
interface LoanScheduleRow { month: number; payment: number; interest: number; principal: number; balance: number; }
interface LoanTerms {
  amount: number; apr: number; termMonths: number; monthlyPayment: number;
  totalInterest: number; totalCost: number; cat: number;
  openingFee?: number; insuranceFee?: number; schedule: LoanScheduleRow[];
}
interface LoanRisk {
  dti: { existing: number | null; withOffer: number | null; cap: number; flag: boolean };
  surplus: { monthly: number; discretionarySpend: number; subscriptions: number; minPayment: number };
  liquidityBufferMonths: number | null;
  relativeCost: { offeredApr: number; worstExistingApr: number; aprFloor: number; worse: boolean };
  incomeStability: { coefficientOfVariation: number; flag: boolean };
  payrollDeduction: { applied: boolean; netPerPeriod: number | null };
  savingsImpact: { goal: string; monthsBefore: number | null; monthsAfter: number | null; delayedMonths: number | null } | null;
  paymentHistory: { available: boolean; onTimeRatio?: number; late?: number; missed?: number; projectedScoreDelta: number };
}
// The consult surface carries the risk panel + warnings under /loan (not the create response).
interface LoansCreateRequest { user_id: string; amount: number; months?: number; loan_request_id?: string; }
interface LoanResponse { status: Status; loan: (LoanTerms & { id: string; userId: string }) | null; issues?: string[]; }

// ---- native REST ----
interface PaymentResponse { status: Status; applied_amount: number; liability: Record<string, unknown> | null; account: Record<string, unknown> | null; transaction: Record<string, unknown> | null; issues: string[]; }
```

---

## 15. Quick reference

| Method | Path | Request | Response | Notes |
|---|---|---|---|---|
| POST | `/api/login` | `{username,password}` | `LoginResponse` / 401 | demo/accesible |
| POST | `/api/session` | `{user_id}` | `SessionResponse` | no auth |
| POST | `/api/message` | `{session_id,text?\|audio_b64?,language}` | `AgentResponse` | render `a2ui` |
| POST | `/api/action` | `{surface_id,name,source_component_id,context}` | `AgentResponse` | `accept_offer` special |
| GET | `/api/ui/{surface_id}` | – | `UiResponse` | hydrated; authoritative |
| POST | `/api/negotiation/{session}/turn` | `{user_id,position}` | `AgentResponse` (`actor`,`round`) | El Revés |
| POST | `/api/negotiation/{session}/take-control` | `{user_id,position}` | `AgentResponse` | El Revés |
| – | `/api/saving-bags*` | – | – | **PENDING TO BE RELEASED — not registered** |
| GET | `/api/profile` | `?user_id` | `ProfileResponse` | native |
| GET | `/api/accounts` | `?user_id` | `AccountsResponse` | native |
| GET | `/api/liabilities` | `?user_id` | `LiabilitiesResponse` | native |
| POST | `/api/liabilities/{id}/payment` | `{user_id,amount,account_id?}` | `PaymentResponse` / 400 | native |
| GET | `/api/audio/{asset_id}` | – | `audio/mpeg` | play speech |
| POST | `/api/loans/greeting` | `{user_id}` | **multipart** payload+audio | loans |
| POST | `/api/loans/consult` | `{session_id,text?\|audio_b64?,language?,loan_request_id?}` | **multipart** payload+audio | loans |
| POST | `/api/loans` | `{user_id,amount,months?,loan_request_id?}` | `LoanResponse` / 400 | create + disburse (manual) |
| GET | `/api/loans/{loan_request_id}` | – | `LoansConsultResponse` | hydrated terminal |
| GET | `/healthz` | – | `{status:"ok"}` | – |
| `*` | `/debug/*` | – | – | **do not use in UI** |
