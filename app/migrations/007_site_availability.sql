CREATE TABLE IF NOT EXISTS site_availability (
    id INTEGER PRIMARY KEY CHECK (id=1),
    site_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
INSERT INTO site_availability(id) VALUES(1) ON CONFLICT DO NOTHING;
CREATE TABLE IF NOT EXISTS site_availability_changes (
    id BIGSERIAL PRIMARY KEY,
    old_enabled BOOLEAN NOT NULL,
    new_enabled BOOLEAN NOT NULL,
    reason VARCHAR(500) NOT NULL CHECK (length(reason)>0),
    actor VARCHAR(64) NOT NULL CHECK (length(actor)>0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
