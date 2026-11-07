SELECT coalesce(utm_campaign, '(none)') AS utm_campaign, count(*) AS deals_won, sum(price) AS revenue
FROM dds.amocrm__leads
WHERE dt BETWEEN DATE '2026-09-22' AND DATE '2026-10-21'
  AND status_id = 142
  AND cast(closed_at AS DATE) = cast(updated_at AS DATE)
GROUP BY ALL
ORDER BY revenue DESC, utm_campaign;
