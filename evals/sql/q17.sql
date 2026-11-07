SELECT operating_system_root, count(*) AS visits
FROM dds.yandex_metrika_logs_api__visits
WHERE dt BETWEEN DATE '2026-10-12' AND DATE '2026-10-18' AND device_category = 2
GROUP BY operating_system_root
ORDER BY visits DESC, operating_system_root;
