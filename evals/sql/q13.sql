SELECT utm_campaign, sum(visits) AS visits
FROM mart.yandex_metrika_logs_api__traffic_daily
WHERE dt BETWEEN DATE '2026-10-01' AND DATE '2026-10-21' AND utm_campaign <> '(none)'
GROUP BY utm_campaign
ORDER BY visits DESC;
