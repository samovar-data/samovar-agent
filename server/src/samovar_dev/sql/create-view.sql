CREATE VIEW {{schema}}.{{name}} AS SELECT * FROM read_parquet({{path}});
