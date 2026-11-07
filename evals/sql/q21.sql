SELECT count(DISTINCT visit_id) AS visits_with_cart_view
FROM dds.yandex_metrika_logs_api__hits
WHERE dt BETWEEN DATE '2026-10-12' AND DATE '2026-10-18' AND url LIKE '%/cart';
