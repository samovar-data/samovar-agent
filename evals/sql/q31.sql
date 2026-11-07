SELECT sum(closed) AS deals_won, sum(closed_price_sum) AS revenue
FROM mart.amocrm__leads_daily
WHERE status_id = 142 AND dt BETWEEN DATE '2026-10-12' AND DATE '2026-10-18';
