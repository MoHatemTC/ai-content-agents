select
tablename,
rowsecurity
from pg_tables
where schemaname='public'
and tablename='workspaces';