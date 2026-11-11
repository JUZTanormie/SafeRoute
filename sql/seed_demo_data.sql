-- Optional demonstration records. Every row is explicitly marked is_demo=1
-- and is excluded from the normal community feed and safety analysis.
INSERT INTO community_reports
(location, category, severity, description, timestamp, author, status, is_demo, source, created_at, updated_at)
VALUES
('Demo location A', 'Poor Lighting', 2, 'DEMO ONLY: example report about an unlit street.', '2026-09-02 20:00', 'SafeRoute demo', 'Reported', 1, 'demo', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
('Demo location B', 'Construction', 2, 'DEMO ONLY: example report about road construction.', '2026-09-02 20:30', 'SafeRoute demo', 'Reported', 1, 'demo', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);
