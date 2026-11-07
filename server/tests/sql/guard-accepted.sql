-- case: mart table
select * from mart.t
-- case: FROM-first syntax
from mart.t select dt
-- case: catalog-qualified view with a trailing semicolon
select * from samovar.mart.t;
-- case: CTE over a mart
with a as (select * from mart.t) select * from a
-- case: detail table with a literal start day
select * from dds.v where dt >= date '2026-10-01'
-- case: detail table between string days
select * from dds.v where dt between '2026-10-01' and '2026-10-10' and x = 1
-- case: detail table with two literal bounds
select * from dds.v where dt >= date '2026-10-15' and dt <= '2026-10-21'
-- case: detail table with a day list
select * from dds.v where dt in ('2026-10-01', '2026-10-02')
-- case: join of a mart and a filtered detail table
select * from mart.t join dds.v using (counter_id) where v.dt = date '2026-10-20'
-- case: allowed table function
select * from range(3)
-- case: set operation
select 1 union all select 2
