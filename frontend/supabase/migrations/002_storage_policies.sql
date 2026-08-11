-- =====================================================
-- Sensei AI
-- Storage Policies
-- Migration 002
-- =====================================================

create policy "Users can upload their own files"
on storage.objects
for insert
to authenticated
with check (
    bucket_id = 'documents'
);

create policy "Users can read their own files"
on storage.objects
for select
to authenticated
using (
    bucket_id = 'documents'
);

create policy "Users can delete their own files"
on storage.objects
for delete
to authenticated
using (
    bucket_id = 'documents'
);