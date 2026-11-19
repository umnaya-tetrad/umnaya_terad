-- Preserve a previously persisted operational pause during upgrade. Money-cap
-- admission itself never toggles this flag; trusted resume is explicit.
UPDATE pilot_processing_budget b SET paused=true FROM pilot_funds f WHERE b.mode=f.mode AND f.paused;
