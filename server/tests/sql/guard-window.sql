-- case: 31 days
select * from dds.v where dt between '2026-09-01' and '2026-10-01'
-- case: 32 days
select * from dds.v where dt between '2026-09-01' and '2026-10-02'
-- case: open start
select * from dds.v where dt >= '2026-09-01'
-- case: custom day column
select * from dds.v where event_day = '2026-10-01'
-- case: wrong day column
select * from dds.v where dt = '2026-10-01'
-- case: views but not CTEs
with a as (select * from mart.t) select * from a join mart.u using (dt)
-- case: computed start
select * from dds.v where dt >= current_date - interval 1 year
-- case: arithmetic on a literal
select * from dds.v where dt >= date '2000-01-01' + 0
-- case: text after the day
select * from dds.v where dt >= '2026-10-01 garbage'
-- case: computed end
select * from dds.v where dt between date '2026-10-01' and current_date
-- case: other table filtered
select * from dds.v as a join dds.w as b using (visit_id) where b.dt = date '2026-10-20'
-- case: both tables filtered
select * from dds.v as a join dds.w as b using (visit_id) where a.dt = date '2026-10-20' and b.dt = date '2026-10-20'
-- case: empty
