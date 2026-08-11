
select
    id,
    owner_id,
    name,
    subject,
    created_at
from public.workspaces
order by created_at desc;