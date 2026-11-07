SELECT page_path, sum(page_views) AS page_views
FROM mart.yandex_metrika_logs_api__pages_daily
WHERE dt BETWEEN DATE '2026-10-01' AND DATE '2026-10-21'
GROUP BY page_path
ORDER BY page_views DESC, page_path
LIMIT 5;
