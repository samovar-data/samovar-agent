SELECT count(*) FILTER (WHERE d.name = 'Дорого') AS expensive,
       count(*) AS lost,
       round(100.0 * count(*) FILTER (WHERE d.name = 'Дорого') / count(*), 1) AS expensive_pct
FROM (
    SELECT *
    FROM dds.amocrm__leads
    WHERE dt BETWEEN DATE '2026-08-07' AND DATE '2026-11-07'
    QUALIFY row_number() OVER (PARTITION BY account_id, lead_id ORDER BY updated_at DESC) = 1
) AS l
JOIN (
    SELECT item_id, name
    FROM dds.amocrm__dictionaries
    WHERE dictionary = 'loss_reason' AND dt = DATE '2026-11-07'  -- the latest daily copy
) AS d ON d.item_id = l.loss_reason_id
WHERE l.status_id = 143 AND l.utm_campaign = 'price_hunters';
