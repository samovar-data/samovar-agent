COPY (
    SELECT
        account_id,
        dt,
        responsible_user_hash,
        pipeline_id,
        status_id,
        cast(count(*) AS bigint) AS leads_changed,
        cast(coalesce(sum(price), 0) AS bigint) AS price_sum,
        cast(coalesce(sum(labor_cost), 0) AS bigint) AS labor_cost_sum,
        cast(count(*) FILTER (WHERE is_deleted) AS bigint) AS deleted,
        cast(count(*) FILTER (WHERE cast(closed_at AS date) = dt) AS bigint) AS closed,
        cast(coalesce(sum(price) FILTER (WHERE cast(closed_at AS date) = dt), 0) AS bigint) AS closed_price_sum
    FROM read_parquet({{source}})
    GROUP BY ALL
    ORDER BY ALL
) TO {{target}} (FORMAT parquet);
