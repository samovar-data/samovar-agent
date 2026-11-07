SELECT sum(visits) AS visits
FROM mart.yandex_metrika_logs_api__traffic_daily
WHERE dt = DATE '2026-10-21';
