SELECT round(sum(new_user_visits) / sum(visits), 4) AS new_user_visit_share
FROM mart.yandex_metrika_logs_api__traffic_daily
WHERE dt BETWEEN DATE '2026-10-12' AND DATE '2026-10-18';
