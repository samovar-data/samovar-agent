COPY (
    WITH hits AS (
        SELECT *,
            CASE WHEN url IS NULL OR url = '' THEN '(none)' ELSE
                coalesce(nullif(regexp_replace(regexp_replace(url, '[?#].*$', ''), '^https?://[^/]+', ''), ''), '/')
            END AS page_path
        FROM read_parquet({{source}})
    )
    SELECT
        counter_id,
        dt,
        page_path,
        cast(count(*) AS bigint) AS events,
        cast(coalesce(sum(page_views), 0) AS bigint) AS page_views,
        cast(count(DISTINCT visit_id) FILTER (WHERE visit_id <> '0') AS bigint) AS visits,
        cast(coalesce(sum(goal_reaches), 0) AS bigint) AS goal_reaches,
        cast(coalesce(sum(link_clicks), 0) AS bigint) AS link_clicks,
        cast(coalesce(sum(downloads), 0) AS bigint) AS downloads,
        cast(coalesce(sum(artificial), 0) AS bigint) AS artificial_events
    FROM hits
    GROUP BY ALL
    ORDER BY ALL
) TO {{target}} (FORMAT parquet);
