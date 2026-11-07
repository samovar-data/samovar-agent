SELECT min(dt) AS first_day, max(dt) AS last_day, count(DISTINCT dt) AS days
FROM mart.yandex_metrika_logs_api__traffic_daily;
