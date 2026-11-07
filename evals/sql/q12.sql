SELECT CASE WHEN isodow(dt) >= 6 THEN 'weekend' ELSE 'weekday' END AS day_type,
       round(sum(visits) / count(DISTINCT dt), 1) AS visits_per_day
FROM mart.yandex_metrika_logs_api__traffic_daily
WHERE dt BETWEEN DATE '2026-09-01' AND DATE '2026-09-30'
GROUP BY day_type
ORDER BY day_type;
