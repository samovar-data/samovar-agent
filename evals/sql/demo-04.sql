WITH leads AS (
    SELECT utm_campaign, count(*) AS leads
    FROM (
        SELECT *
        FROM dds.amocrm__leads
        WHERE dt BETWEEN DATE '2026-08-07' AND DATE '2026-11-07'
        QUALIFY row_number() OVER (PARTITION BY account_id, lead_id ORDER BY updated_at DESC) = 1
    )
    GROUP BY utm_campaign
),
traffic AS (
    SELECT utm_campaign, sum(visits) AS visits
    FROM mart.yandex_metrika_logs_api__traffic_daily
    WHERE dt BETWEEN DATE '2026-08-07' AND DATE '2026-11-07'
    GROUP BY utm_campaign
)
SELECT traffic.utm_campaign, traffic.visits, coalesce(leads.leads, 0) AS leads,
       round(1000.0 * coalesce(leads.leads, 0) / traffic.visits, 1) AS leads_per_1000_visits
FROM traffic LEFT JOIN leads USING (utm_campaign)
ORDER BY leads_per_1000_visits DESC;
