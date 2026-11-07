-- case: no filter
select * from dds.v
-- case: filter weakened by OR
select * from dds.v where dt >= '2026-10-01' or true
-- case: filter outside the subquery that reads the table
select * from (select * from dds.v) where dt >= '2026-10-01'
-- case: filter on another column
select * from dds.v where x = 1
