SELECT round(sum(bounces) / sum(visits), 4) AS bounce_rate
FROM mart.yandex_metrika_logs_api__traffic_daily
WHERE dt BETWEEN DATE '2026-10-12' AND DATE '2026-10-18';
