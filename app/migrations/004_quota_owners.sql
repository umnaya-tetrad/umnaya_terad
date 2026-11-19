-- Persist the first usage day independently of the daily counters.
CREATE TABLE IF NOT EXISTS quota_owners (
    visitor_hash CHAR(64) PRIMARY KEY,
    first_usage_date DATE NOT NULL
);
-- Re-running migrations must never give existing owners another welcome day.
INSERT INTO quota_owners (visitor_hash, first_usage_date)
SELECT visitor_hash, MIN(usage_date) FROM daily_quota_usage GROUP BY visitor_hash
ON CONFLICT (visitor_hash) DO NOTHING;
