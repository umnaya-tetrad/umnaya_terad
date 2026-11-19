ALTER TABLE pilot_funds ADD COLUMN outstanding_debt_rub NUMERIC NOT NULL DEFAULT 0 CHECK(outstanding_debt_rub>=0);
ALTER TABLE pilot_funds ADD CONSTRAINT pilot_wallet_nonnegative CHECK(balance_rub>=0 AND held_rub<=balance_rub);
ALTER TABLE pilot_checks ADD CONSTRAINT pilot_revision_nonnegative CHECK(revision>=0 AND data_revision>=0 AND next_notebook_number>=1);
ALTER TABLE pilot_attempts ADD CONSTRAINT pilot_attempt_nonnegative CHECK(ordinal>=1 AND (actual_cost_rub IS NULL OR actual_cost_rub>=0));
ALTER TABLE pilot_task_analyses ADD COLUMN skipped BOOLEAN NOT NULL DEFAULT false;
