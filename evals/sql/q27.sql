SELECT dt, sum(visits) AS visits
FROM mart.yandex_metrika_logs_api__traffic_daily
WHERE dt BETWEEN DATE '2026-09-01' AND DATE '2026-09-30'
GROUP BY dt
ORDER BY dt;
