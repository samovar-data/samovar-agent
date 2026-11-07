SELECT CASE WHEN dt >= DATE '2026-10-12' THEN 'last_week' ELSE 'previous_week' END AS week,
       sum(visits) AS visits
FROM mart.yandex_metrika_logs_api__traffic_daily
WHERE dt BETWEEN DATE '2026-10-05' AND DATE '2026-10-18'
GROUP BY week
ORDER BY week;
