ALTER TABLE pilot_attempts ADD COLUMN ended_at TIMESTAMPTZ;
ALTER TABLE pilot_attempts ADD COLUMN diagnostics JSONB NOT NULL DEFAULT '{}';
