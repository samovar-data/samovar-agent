-- case: Only read-only SELECT
delete from mart.t
-- case: Only read-only SELECT
copy mart.t to 'x.csv'
-- case: Only read-only SELECT
attach 'x.duckdb' as y
-- case: Only read-only SELECT
pragma version
-- case: Only read-only SELECT
set enable_external_access = true
-- case: Only read-only SELECT
install httpfs
-- case: Exactly one
select 1; select 2
-- case: read_parquet
select * from read_parquet('/etc/x')
-- case: not allowed
select * from 's3://bucket/x.parquet'
-- case: glob
select * from glob('*')
-- case: duckdb_secrets
select * from duckdb_secrets()
-- case: getenv
select getenv('HOME')
-- case: current_setting
select current_setting('s3_secret_access_key')
-- case: main.t
select * from main.t
-- case: schema required
select * from t
-- case: SHOW_REF
describe mart.t
-- case: Unknown view
select * from dds."s3://bucket/raw/x.parquet"
-- case: Unknown view
select * from mart.not_described
-- case: which_secret
select which_secret('s3://bucket/x', 's3')
-- case: getvariable
select getvariable('x')
-- case: read_text
with f as (select * from read_text('/etc/hosts')) select * from f
-- case: glob
select * from (select * from glob('/Users/*')) as g
-- case: read_csv
select * from mart.t, read_csv('/etc/passwd')
-- case: Only read-only SELECT
select * from mart.t; /* trailing */ delete from mart.t
