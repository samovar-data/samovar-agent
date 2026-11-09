CREATE SCHEMA _demo;
CREATE SCHEMA mart;
CREATE TABLE _demo.days AS SELECT DATE '2026-11-06' AS dt, 10 AS visits UNION ALL SELECT DATE '2026-11-07', 20;
CREATE VIEW mart.days AS SELECT * REPLACE ((dt + CAST(getvariable('demo_shift_days') AS INTEGER)) AS dt) FROM _demo.days;
