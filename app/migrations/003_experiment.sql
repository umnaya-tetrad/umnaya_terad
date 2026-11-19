CREATE TABLE IF NOT EXISTS experiment_budget (
 id INTEGER PRIMARY KEY CHECK (id = 1),
 limit_rub NUMERIC(12,6) NOT NULL DEFAULT 300 CHECK (limit_rub >= 0),
 committed_rub NUMERIC(12,6) NOT NULL DEFAULT 0 CHECK (committed_rub >= 0),
 sends INTEGER NOT NULL DEFAULT 0 CHECK (sends >= 0),
 send_limit INTEGER NOT NULL DEFAULT 100,
 paused BOOLEAN NOT NULL DEFAULT FALSE
);
INSERT INTO experiment_budget(id) VALUES (1) ON CONFLICT DO NOTHING;
CREATE TABLE IF NOT EXISTS experiment_attempts (
 id UUID PRIMARY KEY,
 visitor_hash CHAR(64) NOT NULL,
 owner_hash CHAR(64) NOT NULL,
 network_hash CHAR(64) NOT NULL,
 status VARCHAR(40) NOT NULL DEFAULT 'pending',
 charge_rub NUMERIC(12,6) NOT NULL,
 actual_cost_rub NUMERIC(12,6),
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 expires_at TIMESTAMPTZ NOT NULL,
 completed_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS experiment_attempts_owner_created_idx ON experiment_attempts(owner_hash,created_at);
ALTER TABLE experiment_attempts ADD COLUMN IF NOT EXISTS reconciliation_reason VARCHAR(160);
CREATE INDEX IF NOT EXISTS experiment_attempts_network_created_idx ON experiment_attempts(network_hash,created_at);
CREATE INDEX IF NOT EXISTS experiment_attempts_pending_idx ON experiment_attempts(expires_at) WHERE status='pending';
CREATE TABLE IF NOT EXISTS experiment_events (
 event_id UUID PRIMARY KEY,
 visitor_hash CHAR(64) NOT NULL,
 name VARCHAR(64) NOT NULL,
 attempt_id UUID REFERENCES experiment_attempts(id),
 properties JSONB NOT NULL DEFAULT '{}',
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS experiment_events_attempt_idx ON experiment_events(attempt_id);
CREATE UNIQUE INDEX IF NOT EXISTS experiment_first_conversion_idx ON experiment_events(visitor_hash) WHERE name='first_real_analysis_completed';
CREATE UNIQUE INDEX IF NOT EXISTS experiment_pricing_conversion_idx ON experiment_events(visitor_hash,(properties->>'plan_id')) WHERE name='pricing_interest_submitted';
CREATE TABLE IF NOT EXISTS experiment_feedback (
 attempt_id UUID PRIMARY KEY REFERENCES experiment_attempts(id),
 helpful BOOLEAN NOT NULL,
 updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS experiment_pricing_interest (
 visitor_hash CHAR(64) NOT NULL,
 plan_id VARCHAR(16) NOT NULL CHECK (plan_id IN ('practice','intensive')),
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 PRIMARY KEY(visitor_hash,plan_id)
);
