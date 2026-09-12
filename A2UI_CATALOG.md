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

## 2. Message model (v0.9)

All payloads are JSON arrays of messages, each carrying `"version": "v0.9"`:

- `createSurface` — `{ surfaceId, catalogId }`
- `updateComponents` — `{ surfaceId, components: [component, ...] }`
- `updateDataModel` — `{ surfaceId, path, value }`
- `deleteSurface` — `{ surfaceId }`

Components use the A2UI v0.9 **flat adjacency-list** model: a flat list where each entry is `{ "id": string, "component": "<Type>", ...props }` — the type is a **string** and its props are siblings. (The v0.8 nested form `{ "component": { "<Type>": { ... } } }` is **not** used.)

## 3. Data binding

- Any prop value may be a literal or a JSON-Pointer binding: `{ "path": "/finance/liabilities/0/balance" }`.
- Bindings resolve against the surface data model updated by `updateDataModel`.
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
| `ProgressBar` | `value: number \| binding`, `max?: number`, `label?: string` |
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
| `CashFlowTimeline` | `points: { period: string, income: number, expenses: number, net: number }[]` |
| `TradeoffScale` | `leftLabel: string`, `rightLabel: string`, `value: number \| binding` (0–100), `action: Action` |
| `PlanTable` | `months: { month: number, totalBalance: number, payment: number, interest: number, cash: number }[]`, `breakMonth?: number \| null` |
| `BreakAlert` | `month: number`, `shortfall: number`, `reasons?: string[]`, `assumptions?: string[]` |
| `AssumptionChip` | `label: string`, `value: string \| number`, `editable?: boolean`, `path?: string`, `action?: Action` |
| `OfferCard` | `actor: "bank"\|"advocate"`, `headline: string`, `terms: { apr: number, months: number, monthlyPayment: number, totalCost: number }`, `action: Action` |
| `NegotiationTranscript` | `rounds: { round: number, actor: string, summary: string }[]` |
| `QuincenaGauge` | `value: number \| binding`, `min: number`, `max: number`, `label?: string` |
| `GoalJar` | `label: string`, `current: number \| binding`, `target: number \| binding`, `action?: Action` |

## 7. Persistence, placeholders, and revalidation

- Generated surfaces are persisted in `generated_ui` with a `catalog_id`, a `template_json`, and `bindings_json`.
- Persisted templates use `{{path.to.value}}` placeholders (resolved against the database at delivery time). Placeholders carry **data only**.
- Before every delivery the backend hydrates placeholders and runs a **revalidation** pass that may mutate the component structure (for example, inserting a `BreakAlert`). Structure is never treated as static.
- `generated_ui.version` increments on any structural change.

## 8. Shipped subset

Required by milestone:

- **M3:** `Column`, `Row`, `Card`, `Text`, `Heading`, `Divider`, `Badge`, `Button`, `ChoiceGroup`, `Slider`, `DebtNode`, `TradeoffScale`.
- **M4 (added):** `BreakAlert`, `PlanTable`.

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
      "balance": { "path": "/finance/liabilities/0/balance" },
      "apr": { "path": "/finance/liabilities/0/apr" },
      "minPayment": { "path": "/finance/liabilities/0/minPayment" } },
    { "id": "debt-nomina", "component": "DebtNode", "creditor": "BBVA", "kind": "payroll_loan",
      "balance": { "path": "/finance/liabilities/1/balance" },
      "apr": { "path": "/finance/liabilities/1/apr" },
      "minPayment": { "path": "/finance/liabilities/1/minPayment" } },
    { "id": "strategy", "component": "TradeoffScale",
      "leftLabel": "Bajar mi pago mensual", "rightLabel": "Pagar menos intereses",
      "value": { "path": "/ui/strategyTilt" },
      "action": { "event": { "name": "tune_tradeoff", "context": { "value": "/ui/strategyTilt" } } } }
  ] } },
  { "version": "v0.9", "updateDataModel": { "surfaceId": "debt-ana", "path": "/ui", "value": { "strategyTilt": 50 } } }
]
```

## 10. Versioning rules

- Additive, backward-compatible changes (new optional prop, new component) → bump the catalog minor tag and log in `CHANGELOG.md`.
- Renaming/removing a component, prop, or action → breaking change; requires a new catalog ID, frontend confirmation, and a `CHANGELOG.md` entry.
