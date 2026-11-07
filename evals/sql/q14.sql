SELECT round(avg(visit_duration), 1) AS avg_visit_duration_seconds
FROM dds.yandex_metrika_logs_api__visits
WHERE dt BETWEEN DATE '2026-10-12' AND DATE '2026-10-18';
