SELECT browser, count(*) AS visits
FROM dds.yandex_metrika_logs_api__visits
WHERE dt BETWEEN DATE '2026-10-12' AND DATE '2026-10-18'
GROUP BY browser
ORDER BY visits DESC, browser;
