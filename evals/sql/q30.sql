SELECT sum(page_views) AS page_views
FROM mart.yandex_metrika_logs_api__traffic_daily
WHERE dt BETWEEN DATE '2026-10-12' AND DATE '2026-10-18';
