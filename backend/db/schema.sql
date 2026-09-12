-- La Mesa local schema. Single source of truth.
-- Applied with `python -m db.init` (schema + deterministic seed).

CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    age INTEGER,
    city TEXT,
    monthly_income REAL,
    pay_frequency TEXT,
    credit_score INTEGER,
    education_level TEXT,
    created_at TEXT NOT NULL,
    username TEXT,
    password_hash TEXT,
    password_salt TEXT
);

CREATE TABLE IF NOT EXISTS accounts (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    kind TEXT NOT NULL,
    institution TEXT,
    balance REAL NOT NULL DEFAULT 0,
    currency TEXT NOT NULL DEFAULT 'MXN'
);

CREATE TABLE IF NOT EXISTS transactions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    account_id TEXT REFERENCES accounts(id),
    occurred_on TEXT NOT NULL,
    amount REAL NOT NULL,
    direction TEXT NOT NULL,
    category TEXT,
    merchant TEXT,
    is_subscription INTEGER NOT NULL DEFAULT 0,
    memo TEXT
);

CREATE TABLE IF NOT EXISTS saved_recipients (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    alias TEXT NOT NULL,
    clabe TEXT NOT NULL,
    bank_name TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_saved_recipients_user_id ON saved_recipients(user_id);

CREATE TABLE IF NOT EXISTS income_streams (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    source TEXT NOT NULL,
    amount REAL NOT NULL,
    frequency TEXT NOT NULL,
    next_date TEXT
);

CREATE TABLE IF NOT EXISTS subscriptions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    merchant TEXT NOT NULL,
    amount REAL NOT NULL,
    period TEXT NOT NULL,
    next_charge TEXT
);

CREATE TABLE IF NOT EXISTS liabilities (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    creditor TEXT NOT NULL,
    kind TEXT NOT NULL,
    principal REAL NOT NULL,
    balance REAL NOT NULL,
    apr REAL NOT NULL,
    min_payment REAL NOT NULL,
    due_day INTEGER,
    nomina_discount REAL NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'active',
    term_months INTEGER,
    opening_fee REAL DEFAULT 0,
    insurance_fee REAL DEFAULT 0,
    cat REAL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS lender_policies (
    id TEXT PRIMARY KEY,
    creditor TEXT NOT NULL,
    strategy TEXT NOT NULL,
    min_settlement_pct REAL NOT NULL,
    max_months INTEGER NOT NULL,
    apr_floor REAL NOT NULL,
    accepts_consolidation INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS saving_bags (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    name TEXT NOT NULL,
    target_amount REAL,
    target_date TEXT,
    status TEXT NOT NULL DEFAULT 'draft',
    currency TEXT NOT NULL DEFAULT 'MXN',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS saving_bag_answers (
    id TEXT PRIMARY KEY,
    bag_id TEXT NOT NULL REFERENCES saving_bags(id),
    question_key TEXT NOT NULL,
    answer TEXT,
    answered_at TEXT
);

CREATE TABLE IF NOT EXISTS saving_bag_research (
    id TEXT PRIMARY KEY,
    bag_id TEXT NOT NULL REFERENCES saving_bags(id),
    source TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    fetched_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS saving_bag_plan (
    id TEXT PRIMARY KEY,
    bag_id TEXT NOT NULL REFERENCES saving_bags(id),
    plan_json TEXT NOT NULL,
    feasibility TEXT,
    projected_date TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS loan_requests (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    status TEXT NOT NULL DEFAULT 'open',
    context_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS loan_offers (
    id TEXT PRIMARY KEY,
    loan_request_id TEXT NOT NULL,
    user_id TEXT NOT NULL REFERENCES users(id),
    amount REAL NOT NULL,
    apr REAL NOT NULL,
    term_months INTEGER NOT NULL,
    opening_fee REAL NOT NULL DEFAULT 0,
    insurance_fee REAL NOT NULL DEFAULT 0,
    cat REAL NOT NULL DEFAULT 0,
    monthly_payment REAL NOT NULL,
    total_interest REAL NOT NULL DEFAULT 0,
    total_cost REAL NOT NULL DEFAULT 0,
    warnings_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS loans (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    loan_request_id TEXT,
    amount REAL NOT NULL,
    apr REAL NOT NULL,
    term_months INTEGER NOT NULL,
    opening_fee REAL NOT NULL DEFAULT 0,
    insurance_fee REAL NOT NULL DEFAULT 0,
    cat REAL NOT NULL DEFAULT 0,
    monthly_payment REAL NOT NULL,
    total_interest REAL NOT NULL DEFAULT 0,
    total_cost REAL NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS payment_history (
    id TEXT PRIMARY KEY,
    liability_id TEXT NOT NULL REFERENCES liabilities(id),
    due_date TEXT NOT NULL,
    paid_date TEXT,
    amount REAL NOT NULL,
    status TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS generated_ui (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    domain TEXT NOT NULL,
    entity_id TEXT,
    catalog_id TEXT NOT NULL,
    template_json TEXT NOT NULL,
    bindings_json TEXT NOT NULL DEFAULT '{}',
    version INTEGER NOT NULL DEFAULT 1,
    audience TEXT NOT NULL DEFAULT 'user',
    frozen_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ui_actions (
    id TEXT PRIMARY KEY,
    surface_id TEXT NOT NULL,
    user_id TEXT NOT NULL REFERENCES users(id),
    action_name TEXT NOT NULL,
    source_component_id TEXT,
    context_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS negotiation_rounds (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    round_no INTEGER NOT NULL,
    actor TEXT NOT NULL,
    offer_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS accessibility_profiles (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    mode TEXT NOT NULL,
    voice_id TEXT,
    language TEXT NOT NULL DEFAULT 'es-MX',
    speed REAL NOT NULL DEFAULT 1.0,
    enabled_reason TEXT
);

CREATE TABLE IF NOT EXISTS audio_assets (
    id TEXT PRIMARY KEY,
    user_id TEXT REFERENCES users(id),
    surface_id TEXT,
    text TEXT NOT NULL,
    text_hash TEXT NOT NULL,
    voice_id TEXT,
    file_path TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    active_surface_id TEXT,
    context_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS traces (
    id TEXT PRIMARY KEY,
    trace_id TEXT NOT NULL,
    parent_id TEXT,
    kind TEXT NOT NULL,
    name TEXT NOT NULL,
    provider TEXT,
    model TEXT,
    latency_ms INTEGER,
    tokens INTEGER,
    error TEXT,
    payload_json TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_accounts_user ON accounts(user_id);
CREATE INDEX IF NOT EXISTS idx_transactions_user ON transactions(user_id);
CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions(occurred_on);
CREATE INDEX IF NOT EXISTS idx_income_user ON income_streams(user_id);
CREATE INDEX IF NOT EXISTS idx_subscriptions_user ON subscriptions(user_id);
CREATE INDEX IF NOT EXISTS idx_liabilities_user ON liabilities(user_id);
CREATE INDEX IF NOT EXISTS idx_saving_bags_user ON saving_bags(user_id);
CREATE INDEX IF NOT EXISTS idx_generated_ui_user ON generated_ui(user_id);
CREATE INDEX IF NOT EXISTS idx_loan_requests_user ON loan_requests(user_id);
CREATE INDEX IF NOT EXISTS idx_loan_offers_request ON loan_offers(loan_request_id);
CREATE INDEX IF NOT EXISTS idx_loans_user ON loans(user_id);
CREATE INDEX IF NOT EXISTS idx_payment_history_liability ON payment_history(liability_id);
CREATE INDEX IF NOT EXISTS idx_generated_ui_domain ON generated_ui(domain, entity_id);
CREATE INDEX IF NOT EXISTS idx_ui_actions_surface ON ui_actions(surface_id);
CREATE INDEX IF NOT EXISTS idx_negotiation_session ON negotiation_rounds(session_id);
CREATE INDEX IF NOT EXISTS idx_audio_text_hash ON audio_assets(text_hash);
CREATE INDEX IF NOT EXISTS idx_traces_trace_id ON traces(trace_id);
