COPY (
    SELECT
        counter_id,
        dt,
        coalesce(traffic_source, '(none)') AS traffic_source,
        attribution_model,
        CASE device_category
            WHEN 1 THEN 'desktop'
            WHEN 2 THEN 'mobile'
            WHEN 3 THEN 'tablet'
            WHEN 4 THEN 'tv'
            ELSE 'unknown'
        END AS device,
        coalesce(nullif(utm_source, ''), '(none)') AS utm_source,
        coalesce(nullif(utm_medium, ''), '(none)') AS utm_medium,
        coalesce(nullif(utm_campaign, ''), '(none)') AS utm_campaign,
        cast(count(*) AS bigint) AS visits,
        cast(coalesce(sum(page_views), 0) AS bigint) AS page_views,
        cast(coalesce(sum(bounce), 0) AS bigint) AS bounces,
        cast(coalesce(sum(is_new_user), 0) AS bigint) AS new_user_visits
    FROM read_parquet({{source}})
    GROUP BY ALL
    ORDER BY ALL
) TO {{target}} (FORMAT parquet);
