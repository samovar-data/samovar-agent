SELECT utm_campaign, count(*) AS won, round(avg(date_diff('day', created_at, closed_at)), 1) AS avg_days_to_won
FROM (
    SELECT *
    FROM dds.amocrm__leads
    WHERE dt BETWEEN DATE '2026-08-07' AND DATE '2026-11-07'
    QUALIFY row_number() OVER (PARTITION BY account_id, lead_id ORDER BY updated_at DESC) = 1
)
WHERE status_id = 142 AND closed_at IS NOT NULL
GROUP BY utm_campaign
ORDER BY avg_days_to_won;
