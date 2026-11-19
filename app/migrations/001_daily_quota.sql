-- Псевдонимный дневной лимит. Фото, IP и ответы модели здесь не хранятся.
CREATE TABLE IF NOT EXISTS daily_quota_usage (
    visitor_hash CHAR(64) NOT NULL,
    usage_date DATE NOT NULL,
    completed_count INTEGER NOT NULL DEFAULT 0 CHECK (completed_count >= 0),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (visitor_hash, usage_date)
);

CREATE TABLE IF NOT EXISTS daily_quota_reservations (
    id UUID PRIMARY KEY,
    visitor_hash CHAR(64) NOT NULL,
    usage_date DATE NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('pending', 'completed', 'released')),
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    settled_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS daily_quota_reservations_active_idx
    ON daily_quota_reservations (visitor_hash, usage_date, state, expires_at);
