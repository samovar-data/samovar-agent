SELECT regexp_replace(start_url, '^https?://[^/]+', '') AS entry_page, count(*) AS visits
FROM dds.yandex_metrika_logs_api__visits
WHERE dt BETWEEN DATE '2026-10-12' AND DATE '2026-10-18'
GROUP BY entry_page
ORDER BY visits DESC, entry_page
LIMIT 5;
