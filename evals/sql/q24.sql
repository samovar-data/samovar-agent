SELECT social_network, count(*) AS visits
FROM dds.yandex_metrika_logs_api__visits
WHERE dt BETWEEN DATE '2026-09-22' AND DATE '2026-10-21' AND social_network IS NOT NULL
GROUP BY social_network
ORDER BY visits DESC;
