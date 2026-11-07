SELECT utm_source, sum(visits) AS visits
FROM mart.yandex_metrika_logs_api__traffic_daily
WHERE utm_campaign = 'autumn_sale'
GROUP BY utm_source
ORDER BY visits DESC;
