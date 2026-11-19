-- Operational changes only; never reset spend, sends or the independent price pause.
CREATE TABLE IF NOT EXISTS experiment_budget_changes (
    id BIGSERIAL PRIMARY KEY,
    old_limit_rub NUMERIC(12,6) NOT NULL CHECK (old_limit_rub >= 0),
    new_limit_rub NUMERIC(12,6) NOT NULL CHECK (new_limit_rub >= 0),
    old_send_limit INTEGER NOT NULL CHECK (old_send_limit >= 0),
    new_send_limit INTEGER NOT NULL CHECK (new_send_limit >= 0),
    reason VARCHAR(500) NOT NULL CHECK (length(reason) > 0),
    actor VARCHAR(64) NOT NULL CHECK (length(actor) > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
