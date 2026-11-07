SELECT dt, sum(visits) AS visits FROM dds.visits WHERE dt BETWEEN DATE '2026-10-21' AND DATE '2026-10-21' GROUP BY dt
