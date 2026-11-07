SELECT hour(occurred_at) AS hour, count(*) AS events
FROM dds.yandex_metrika_logs_api__hits
WHERE dt = DATE '2026-10-21'
GROUP BY hour
ORDER BY hour;
