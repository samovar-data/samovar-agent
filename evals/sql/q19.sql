SELECT round(count(*) FILTER (WHERE list_contains(goals_id, 1002)) / count(*), 4) AS checkout_conversion
FROM dds.yandex_metrika_logs_api__visits
WHERE dt BETWEEN DATE '2026-10-12' AND DATE '2026-10-18';
