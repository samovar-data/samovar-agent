WITH current AS (
    SELECT *
    FROM dds.amocrm__leads
    WHERE dt BETWEEN DATE '2026-08-07' AND DATE '2026-11-07'
    QUALIFY row_number() OVER (PARTITION BY account_id, lead_id ORDER BY updated_at DESC) = 1
),
revenue AS (
    SELECT utm_campaign, sum(price) AS revenue
    FROM current
    WHERE status_id = 142
    GROUP BY utm_campaign
),
traffic AS (
    SELECT utm_campaign, sum(visits) AS visits
    FROM mart.yandex_metrika_logs_api__traffic_daily
    WHERE dt BETWEEN DATE '2026-08-07' AND DATE '2026-11-07'
    GROUP BY utm_campaign
)
SELECT traffic.utm_campaign, traffic.visits, coalesce(revenue.revenue, 0) AS revenue,
       round(coalesce(revenue.revenue, 0) / traffic.visits, 1) AS revenue_per_visit
FROM traffic LEFT JOIN revenue USING (utm_campaign)
ORDER BY revenue_per_visit DESC;
