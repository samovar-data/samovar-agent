SELECT schema_name, view_name
FROM duckdb_views()
WHERE database_name = 'samovar' AND NOT internal
ORDER BY schema_name, view_name;
