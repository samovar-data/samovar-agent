SELECT adv_engine, count(*) AS visits
FROM dds.yandex_metrika_logs_api__visits
WHERE dt BETWEEN DATE '2026-10-01' AND DATE '2026-10-21' AND traffic_source = 'ad'
GROUP BY adv_engine
ORDER BY visits DESC;
