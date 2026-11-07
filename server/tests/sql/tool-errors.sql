-- case: Only read-only SELECT
DELETE FROM mart.yandex_metrika_logs_api__traffic_daily
-- case: must filter
SELECT * FROM dds.yandex_metrika_logs_api__visits
-- case: nope
SELECT nope FROM mart.yandex_metrika_logs_api__traffic_daily
