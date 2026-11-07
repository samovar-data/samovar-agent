SELECT search_engine_root, count(*) AS visits
FROM dds.yandex_metrika_logs_api__visits
WHERE dt BETWEEN DATE '2026-10-01' AND DATE '2026-10-21' AND traffic_source = 'organic'
GROUP BY search_engine_root
ORDER BY visits DESC;
