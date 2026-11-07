SELECT page_path, sum(goal_reaches) AS goal_reaches
FROM mart.yandex_metrika_logs_api__pages_daily
WHERE dt BETWEEN DATE '2026-10-12' AND DATE '2026-10-18' AND goal_reaches > 0
GROUP BY page_path
ORDER BY goal_reaches DESC, page_path;
