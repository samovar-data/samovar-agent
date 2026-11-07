SELECT count(*) AS checkout_visits
FROM dds.yandex_metrika_logs_api__visits
WHERE dt BETWEEN DATE '2026-10-12' AND DATE '2026-10-18' AND list_contains(goals_id, 1002);
