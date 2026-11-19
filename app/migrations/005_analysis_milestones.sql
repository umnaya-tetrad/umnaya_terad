-- A consented display of an owned successful attempt, independent of event retries.
CREATE TABLE IF NOT EXISTS experiment_analysis_views (
    visitor_hash CHAR(64) NOT NULL,
    attempt_id UUID NOT NULL REFERENCES experiment_attempts(id),
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (visitor_hash, attempt_id)
);
-- Preserve earlier displays without turning a replay into a new milestone.
INSERT INTO experiment_analysis_views(visitor_hash, attempt_id, recorded_at)
SELECT e.visitor_hash, e.attempt_id, MIN(e.created_at)
FROM experiment_events e JOIN experiment_attempts a
  ON a.id=e.attempt_id AND a.visitor_hash=e.visitor_hash AND a.status='ok'
WHERE e.name='analysis_result_shown'
  AND e.properties->>'source'='real'
  AND e.properties->>'status'='ok'
GROUP BY e.visitor_hash, e.attempt_id
ON CONFLICT DO NOTHING;
CREATE UNIQUE INDEX IF NOT EXISTS experiment_analysis_milestone_idx
ON experiment_events(visitor_hash, name)
WHERE name IN ('second_real_analysis_completed','third_real_analysis_completed',
              'returning_day_analysis_completed','welcome_quota_completed');
