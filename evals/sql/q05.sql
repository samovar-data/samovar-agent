SELECT device, sum(visits) AS visits, round(sum(bounces) / sum(visits), 4) AS bounce_rate
FROM mart.yandex_metrika_logs_api__traffic_daily
WHERE dt BETWEEN DATE '2026-09-22' AND DATE '2026-10-21'
GROUP BY device
ORDER BY visits DESC;
