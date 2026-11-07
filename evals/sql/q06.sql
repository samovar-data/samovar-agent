SELECT round(sum(visits) FILTER (WHERE device = 'mobile') / sum(visits), 4) AS mobile_share
FROM mart.yandex_metrika_logs_api__traffic_daily
WHERE dt BETWEEN DATE '2026-10-01' AND DATE '2026-10-21';
