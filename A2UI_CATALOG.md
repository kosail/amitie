# A2UI_CATALOG.md — Interface Contract

> **Authority:** `INVARIANTS.md` > `SPECS.md` > this file > `AGENTS.md`.
> This is the **frozen contract** between the backend (which generates A2UI) and the frontend (which renders it). Component names, props, action names, and message conventions here are authoritative. Changing them is a breaking change and MUST be recorded in `CHANGELOG.md`.
>
> Built against **A2UI v0.9** message types and the **flat component format** introduced in v0.9 (`"component": "Text"` with sibling props). Payloads are validated with `jsonschema` against the A2UI SDK's vendored v0.9 schemas plus `ui_contract/catalog.schema.json`; if the schemas reject a shape, the schemas win and this document is corrected.

---

## 1. Catalogs

| Catalog ID | Purpose |
|---|---|
| `amitie.standard.v1` | Default interface for all users |
| `amitie.voz-color.v1` | Accessible interface: high contrast, icon-first, large targets, TTS-first (activated by `accessibility_profiles` flags) |

A surface declares exactly one catalog in `createSurface`. The agent may switch catalogs between surfaces but never mixes components from two catalogs in one surface.

`amitie.voz-color.v1` reuses the standard component set (its catalog extends `amitie.standard.v1`) and is distinguished by its catalog ID, which the frontend keys accessible styling and layout on. It is selected **automatically** from `accessibility_profiles`; the user never toggles it.

## 2. Message model (v0.9)

All payloads are JSON arrays of messages, each carrying `"version": "v0.9"`:

- `createSurface` — `{ surfaceId, catalogId }`
- `updateComponents` — `{ surfaceId, components: [component, ...] }`
- `updateDataModel` — `{ surfaceId, path, value }`
- `deleteSurface` — `{ surfaceId }`

Components use the A2UI v0.9 **flat adjacency-list** model: a flat list where each entry is `{ "id": string, "component": "<Type>", ...props }` — the type is a **string** and its props are siblings. (The v0.8 nested form `{ "component": { "<Type>": { ... } } }` is **not** used.)

## 3. Data binding

- Any prop value may be a literal or a JSON-Pointer binding: `{ "path": "/liabilities/0/balance" }`.
- Bindings resolve against the surface data model updated by `updateDataModel`. The data model root holds the domain keys directly — `profile`, `liabilities`, `totals`, `incomeStreams`, `subscriptions`, `subscriptionTotal`, `cashFlow`, `plan`, `speech`, `audience` — with no `/finance` wrapper.
- `audience` is a backend-computed `{level: simple|standard|detailed, ...}` object describing how simple the UI must be for this user (age, accessibility, education, activity). The LLM adapts to it; the frontend may use it to adjust density. It never substitutes for the required `LoanOffer.amount`.
- The backend never embeds a literal financial value in a persisted template; it uses bindings or `{{...}}` placeholders (see §7).

## 4. Actions

Interactive components carry an action:

```json
{ "action": { "event": { "name": "<action_name>", "context": { "field": "/json/pointer" } } } }
```

On interaction the client sends the standard A2UI action to the backend:

```json
{ "name": "<action_name>", "surfaceId": "...", "sourceComponentId": "...", "timestamp": "...", "context": { ... } }
```

All five fields are required. Defined action names:

| Action name | Emitted by | Meaning |
|---|---|---|
| `select_strategy` | `ChoiceGroup` | User picked a restructuring strategy |
| `tune_tradeoff` | `TradeoffScale`, `Slider` | User adjusted the goal tradeoff |
| `request_simulation` | `Button` | Re-run the plan with current inputs |
| `approve_plan` | `Button` | Accept the current plan |
| `toggle_assumption` | `AssumptionChip` | Edit an exposed assumption (Caja de Cristal) |
| `take_control` | `Button` | User seizes the El Revés negotiation |
| `accept_offer` | `OfferCard` | Accept a negotiated offer |
| `request_loan` | `LoanOffer` | User accepts the offered loan (frontend then calls `POST /api/loans`) |
| `refresh_bag` | `Button` | *(reserved — Saving Bags pending)* |
| `adjust_goal` | `Slider`, `TextField` | *(reserved — Saving Bags pending)* |

## 5. Component catalog — primitives

| Type | Props |
|---|---|
| `Column` | `children: string[]`, `gap?: number`, `align?: "start"\|"center"\|"end"`, `justify?: "start"\|"center"\|"between"` |
| `Row` | `children: string[]`, `gap?: number`, `align?: string`, `justify?: string` |
| `Card` | `children?: string[]`, `title?: string`, `tone?: "neutral"\|"positive"\|"warning"\|"danger"` |
| `List` | `children: string[]`, `ordered?: boolean` |
| `Text` | `text: string \| binding`, `variant?: "body"\|"muted"\|"caption"`, `tone?: string` |
| `Heading` | `text: string`, `level?: 1\|2\|3` |
| `Divider` | `{}` |
| `Badge` | `label: string`, `tone?: "neutral"\|"positive"\|"warning"\|"danger"` |
| `ProgressBar` | `value: number \| binding`, `max?: number \| binding`, `label?: string` |
| `Button` | `label: string`, `variant?: "primary"\|"secondary"\|"ghost"\|"danger"`, `action: Action` |
| `ChoiceGroup` | `options: { value: string, label: string, description?: string }[]`, `value: string \| binding`, `multiple?: boolean`, `action: Action` |
| `Slider` | `min: number`, `max: number`, `step?: number`, `value: number \| binding`, `label?: string`, `action: Action` |
| `TextField` | `label: string`, `value: string \| binding`, `placeholder?: string`, `action: Action` |
| `CheckBox` | `label: string`, `checked: boolean \| binding`, `action: Action` |
| `Sheet` | `child: string`, `title?: string`, `open: boolean \| binding` |

## 6. Component catalog — domain

| Type | Props |
|---|---|
| `DebtNode` | `creditor: string`, `balance: number \| binding`, `apr: number \| binding`, `minPayment: number \| binding`, `kind?: string`, `badge?: string` |
| `CashFlowTimeline` | `points: { period: string, income: number, expenses: number, net: number }[]` *(reserved — Saving Bags pending)* |
| `TradeoffScale` | `leftLabel: string`, `rightLabel: string`, `value: number \| binding` (0–100), `action: Action` |
| `PlanTable` | `months: { month: number, totalBalance: number, payment: number, interest: number, cash: number }[]`, `breakMonth?: number \| null` |
| `BreakAlert` | `month: number`, `shortfall: number`, `reasons?: string[]`, `assumptions?: string[]` |
| `AssumptionChip` | `label: string`, `value: string \| number`, `editable?: boolean`, `path?: string`, `action?: Action` |
| `OfferCard` | `actor: "bank"\|"advocate"`, `headline: string`, `terms: { apr: number, months: number, monthlyPayment: number, totalCost: number }`, `action: Action` |
| `NegotiationTranscript` | `rounds: { round: number, actor: string, summary: string }[]` |
| `QuincenaGauge` | `value: number \| binding`, `min: number`, `max: number`, `label?: string` |
| `GoalJar` | `label: string \| binding`, `current: number \| binding`, `target: number \| binding`, `action?: Action` *(reserved — Saving Bags pending)* |
| `LineChart` | `points: { label: string, value: number }[] \| binding`, `title?: string`, `yLabel?: string` |
| `BarChart` | `bars: { label: string, value: number }[] \| binding`, `title?: string` |
| `ForecastChart` | `forecast: { period: string, value: number }[] \| binding`, `actual?: { period: string, value: number }[] \| binding`, `title?: string` |
| `ScenarioComparison` | `scenarios: { label: string, monthlyPayment: number, payoffMonths: number, totalInterest: number, interestSaved?: number, monthsSaved?: number }[] \| binding`, `highlightIndex?: number`, `title?: string` |
| `LoanOffer` | `amount: number \| binding`, `apr: number \| binding`, `months: number \| binding`, `monthlyPayment: number \| binding`, `totalInterest: number \| binding`, `cat: number \| binding`, `totalCost?: number \| binding`, `schedule?: { month, payment, interest, principal, balance }[] \| binding`, `action?: Action` |

## 7. Persistence, placeholders, and revalidation

- Generated surfaces are persisted in `generated_ui` with a `catalog_id`, a `template_json`, and `bindings_json`.
- Persisted templates use `{{path.to.value}}` placeholders (resolved against the database at delivery time). Placeholders carry **data only**.
- The Loans & Credits consult flow also stores a `data_model` snapshot with the surface; it is merged into the resolution context on delivery (live values win on key overlap). See `LOANS_CONSULT_GUIDE.md`.
- Before every delivery the backend hydrates placeholders and runs a **revalidation** pass that may mutate the component structure (for example, inserting a `BreakAlert`). Structure is never treated as static.
- `generated_ui.version` increments on any structural change.

## 8. Shipped subset

Required by milestone:

- **M3:** `Column`, `Row`, `Card`, `Text`, `Heading`, `Divider`, `Badge`, `Button`, `ChoiceGroup`, `Slider`, `DebtNode`, `TradeoffScale`.
- **M4 (added):** `BreakAlert`, `PlanTable`.
- **M5 (added):** `OfferCard`, `NegotiationTranscript`.
- **M6:** `List`, `ProgressBar`, `TextField` (generic).
- **PENDING TO BE RELEASED:** `CashFlowTimeline`, `GoalJar` (staged with Saving Bags; not emitted).
- **M8 (added):** `AssumptionChip` (Caja de Cristal).
- **Loans (added):** `LineChart`, `BarChart`, `ForecastChart`, `ScenarioComparison`, `LoanOffer` (engine-backed offer + risk for the loans consult).

**Loans terminal subset (mobile-supported).** The loans consult emits only:
`Column, Row, Card, Text, Heading, Divider, Badge, Button, ProgressBar, List,
ScenarioComparison, PlanTable, ForecastChart, LineChart, BreakAlert, LoanOffer`.
Canonical item shapes are in `API_KNOWLEDGE.md` §6. The backend normalizes model
output (`ui_contract/normalize.py`) so `action` is always an object and numeric
props are literals or `{"path": ...}` bindings before validation (`REQ-LM-13`).
In a **loans terminal**, `ScenarioComparison.scenarios` carries the offered loan's
**payment-term (plazo) options** (`label` = "N meses", `payoffMonths` = term
months, `monthlyPayment`, `totalInterest`), computed by `engine/loan_offer.py`
(`term_options`). The candidate set is **amount-banded** (`allowed_terms_for`: a
small loan only offers short plazos), always including the selected term and any
term the user explicitly asked for. The selected term (passed as `highlightIndex`)
is the user's requested term when they gave one, otherwise `recommend_term`'s
per-applicant pick (profile, payment likelihood/behavior, requested amount) —
never a fixed term — and the selected scenario may carry `requested: true` and an
optional `note` with the plain-language reason. The offer itself
(`LoanOffer.termMonths` and its payment/interest/CAT/schedule) is presented at the
selected plazo. A user-stated term is confirmed (with its real implications)
before the terminal is offered. Debt-payoff scenarios (`analyze_loans`) remain in
the La Mesa / El Revés flows, not in the loans terminal.

Everything else in §6 is reserved for later milestones and must not be emitted until the frontend confirms support. Adding components is additive (see §10), so the catalog ID remains `amitie.standard.v1`.

## 9. Example — La Mesa debt surface

```json
[
  { "version": "v0.9", "createSurface": { "surfaceId": "debt-ana", "catalogId": "amitie.standard.v1" } },
  { "version": "v0.9", "updateComponents": { "surfaceId": "debt-ana", "components": [
    { "id": "root", "component": "Column", "children": ["title", "debts", "strategy"], "gap": 16 },
    { "id": "title", "component": "Heading", "text": "Tu situación actual", "level": 1 },
    { "id": "debts", "component": "Column", "children": ["debt-bbva", "debt-nomina"], "gap": 8 },
    { "id": "debt-bbva", "component": "DebtNode", "creditor": "BBVA", "kind": "credit_card",
      "balance": { "path": "/liabilities/0/balance" },
      "apr": { "path": "/liabilities/0/apr" },
      "minPayment": { "path": "/liabilities/0/minPayment" } },
    { "id": "debt-nomina", "component": "DebtNode", "creditor": "BBVA", "kind": "payroll_loan",
      "balance": { "path": "/liabilities/1/balance" },
      "apr": { "path": "/liabilities/1/apr" },
      "minPayment": { "path": "/liabilities/1/minPayment" } },
    { "id": "strategy", "component": "TradeoffScale",
      "leftLabel": "Bajar mi pago mensual", "rightLabel": "Pagar menos intereses",
      "value": 50,
      "action": { "event": { "name": "tune_tradeoff", "context": { "value": 50 } } } }
  ] } },
  { "version": "v0.9", "updateDataModel": { "surfaceId": "debt-ana", "path": "/", "value": { "liabilities": [ { "balance": 48000, "apr": 0.54, "minPayment": 2900 } ] } } }
]
```

## 10. Versioning rules

- Additive, backward-compatible changes (new optional prop, new component) → bump the catalog minor tag and log in `CHANGELOG.md`.
- Renaming/removing a component, prop, or action → breaking change; requires a new catalog ID, frontend confirmation, and a `CHANGELOG.md` entry.

## 11. Audio & speech

A2UI v0.9 has no audio message type, so speech rides the surface **data model** plus the HTTP response:

- In accessible mode (`amitie.voz-color.v1`), every emitted surface carries a `/speech` object:
  `{ "text": string, "audioRef": "/api/audio/{asset_id}", "provider": string }`.
- The `audioRef` points at the `voice` MCP-generated asset, cached by text hash. The frontend fetches it via `GET /api/audio/{asset_id}` and plays it.
- Spoken numbers are normalized **for synthesis only**: grouping separators, currency, and trailing cents are rewritten into the Spanish spoken form before the TTS provider (`$1,000.00` → `1000 pesos`, spoken "mil pesos"; `5,000–200,000 MXN` → "cinco mil a doscientos mil pesos"), because engines like the local Piper/espeak path read `$` as "dólar" and `,` as "coma". The audio cache is keyed on this spoken form (`speech-v2`), while `/speech.text` and `GET /api/audio` metadata keep the original formatting, so the UI still shows `$1,000.00`.
- Mutation responses (`POST /api/message`, `/api/action`, negotiation, loans, `GET /api/ui/{id}`) additionally expose a top-level `audio_ref` field for convenience.
- Audio **input** is transcribed through the `voice` MCP (`transcribe_audio`) before the agent interprets it; the transcription is treated as the user's `text`.
