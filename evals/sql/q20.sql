SELECT round(avg(page_views), 2) AS pages_per_visit
FROM dds.yandex_metrika_logs_api__visits
WHERE dt BETWEEN DATE '2026-10-12' AND DATE '2026-10-18';
