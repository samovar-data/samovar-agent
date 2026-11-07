SELECT dt, sum(visits) AS visits FROM mart.yandex_metrika_logs_api__traffic_daily
WHERE dt BETWEEN '2026-10-12' AND '2026-10-18'
GROUP BY dt
ORDER BY dt
