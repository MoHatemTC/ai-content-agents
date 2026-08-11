-- =====================================================
-- Sensei AI
-- Initial Database Schema
-- Migration 001
-- =====================================================

create extension if not exists vector;

-- =====================================================
-- ENUMS
-- =====================================================

create type app_role as enum (
    'student',
    'reviewer',
    'admin'
);

create type document_status as enum (
    'uploaded',
    'parsing',
    'embedding',
    'indexed',
    'failed'
);

create type generation_kind as enum (
    'question_bank',
    'flashcards',
    'study_plan',
    'revision_sheet',
    'test_help'
);

create type review_status as enum (
    'pending',
    'approved',
    'rejected',
    'needs_edit'
);

create type chat_kind as enum (
    'mentor',
    'concept'
);

-- =====================================================
-- PROFILES
-- =====================================================

create table public.profiles (
    id uuid primary key references auth.users(id) on delete cascade,

    full_name text not null,
    initials text not null,
    avatar_url text,

    created_at timestamptz not null default now()
);

-- =====================================================
-- USER ROLES
-- =====================================================

create table public.user_roles (
    id uuid primary key default gen_random_uuid(),

    user_id uuid not null
        references public.profiles(id)
        on delete cascade,

    role app_role not null default 'student',

    created_at timestamptz not null default now(),

    unique(user_id, role)
);

-- =====================================================
-- WORKSPACES
-- =====================================================

create type workspace_accent as enum (
    'primary',
    'info',
    'success',
    'warning'
);

create table public.workspaces (
    id uuid primary key default gen_random_uuid(),

    owner_id uuid not null
        references public.profiles(id)
        on delete cascade,

    name text not null,
    subject text not null,
    description text,

    accent workspace_accent,

    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

-- =====================================================
-- DOCUMENTS
-- =====================================================

create table public.documents (
    id uuid primary key default gen_random_uuid(),

    workspace_id uuid not null
        references public.workspaces(id)
        on delete cascade,

    uploaded_by uuid not null
        references public.profiles(id)
        on delete cascade,

    title text not null,

    kind text not null,

    size_bytes bigint,

    pages integer,

    chunk_count integer not null default 0,

    status document_status not null default 'uploaded',

    storage_path text,

    notes text,

    topics text[] not null default '{}',

    coverage numeric(5,2),

    created_at timestamptz not null default now()
);

-- =====================================================
-- CHUNKS
-- =====================================================

create table public.chunks (
    id uuid primary key default gen_random_uuid(),

    document_id uuid not null
        references public.documents(id)
        on delete cascade,

    workspace_id uuid not null
        references public.workspaces(id)
        on delete cascade,

    chunk_index integer not null,

    page integer,

    content text not null,

    token_count integer,

    created_at timestamptz not null default now(),

    unique(document_id, chunk_index)
);

-- =====================================================
-- EMBEDDINGS
-- =====================================================

create table public.embeddings (
    id uuid primary key default gen_random_uuid(),

    chunk_id uuid not null
        references public.chunks(id)
        on delete cascade,

    embedding vector(1536) not null,

    model text not null,

    created_at timestamptz not null default now(),

    unique(chunk_id)
);

-- =====================================================
-- GENERATIONS
-- =====================================================

create table public.generations (
    id uuid primary key default gen_random_uuid(),

    workspace_id uuid not null
        references public.workspaces(id)
        on delete cascade,

    created_by uuid not null
        references public.profiles(id)
        on delete cascade,

    kind generation_kind not null,

    model text not null,

    title text not null,

    payload jsonb not null,

    document_ids uuid[] not null default '{}',

    grounding_score numeric(5,2),

    quality_score numeric(5,2),

    review_status review_status not null default 'pending',

    created_at timestamptz not null default now()
);

-- =====================================================
-- GENERATION VERSIONS
-- =====================================================

create table public.generation_versions (
    id uuid primary key default gen_random_uuid(),

    generation_id uuid not null
        references public.generations(id)
        on delete cascade,

    version integer not null,

    payload jsonb not null,

    edited_by uuid
        references public.profiles(id)
        on delete set null,

    created_at timestamptz not null default now(),

    unique(generation_id, version)
);

-- =====================================================
-- REVIEWS
-- =====================================================

create table public.reviews (
    id uuid primary key default gen_random_uuid(),

    generation_id uuid not null
        references public.generations(id)
        on delete cascade,

    workspace_id uuid not null
        references public.workspaces(id)
        on delete cascade,

    item_id text not null,

    reviewer_id uuid
        references public.profiles(id)
        on delete set null,

    status review_status not null default 'pending',

    comment text,

    created_at timestamptz not null default now()
);

-- =====================================================
-- CHATS
-- =====================================================

create table public.chats (
    id uuid primary key default gen_random_uuid(),

    workspace_id uuid not null
        references public.workspaces(id)
        on delete cascade,

    user_id uuid not null
        references public.profiles(id)
        on delete cascade,

    kind chat_kind not null,

    title text not null,

    model text not null,

    created_at timestamptz not null default now()
);

-- =====================================================
-- CHAT MESSAGES
-- =====================================================

create table public.chat_messages (
    id uuid primary key default gen_random_uuid(),

    chat_id uuid not null
        references public.chats(id)
        on delete cascade,

    role text not null
        check (role in ('user','assistant','system')),

    content text not null,

    citations jsonb,

    created_at timestamptz not null default now()
);

-- =====================================================
-- NOTIFICATIONS
-- =====================================================

create table public.notifications (
    id uuid primary key default gen_random_uuid(),

    user_id uuid
        references public.profiles(id)
        on delete cascade,

    workspace_id uuid
        references public.workspaces(id)
        on delete cascade,

    roles app_role[] not null default '{}',

    kind text not null,

    title text not null,

    body text not null,

    read boolean not null default false,

    created_at timestamptz not null default now()
);

-- =====================================================
-- HISTORY
-- =====================================================

create table public.history (
    id uuid primary key default gen_random_uuid(),

    workspace_id uuid not null
        references public.workspaces(id)
        on delete cascade,

    user_id uuid not null
        references public.profiles(id)
        on delete cascade,

    generation_id uuid
        references public.generations(id)
        on delete set null,

    kind generation_kind not null,

    title text not null,

    model text not null,

    review_status review_status not null,

    created_at timestamptz not null default now()
);

-- =====================================================
-- ANALYTICS
-- =====================================================

create table public.analytics (
    workspace_id uuid primary key
        references public.workspaces(id)
        on delete cascade,

    documents integer not null default 0,

    generations integer not null default 0,

    approvals integer not null default 0,

    rejections integer not null default 0,

    avg_grounding numeric(5,2) not null default 0,

    avg_quality numeric(5,2) not null default 0,

    captured_at timestamptz not null default now()
);

-- =====================================================
-- INDEXES
-- =====================================================

create index idx_workspaces_owner
on public.workspaces(owner_id);

create index idx_documents_workspace
on public.documents(workspace_id);

create index idx_chunks_document
on public.chunks(document_id);

create index idx_chunks_workspace
on public.chunks(workspace_id);

create index idx_embeddings_chunk
on public.embeddings(chunk_id);

create index idx_generations_workspace
on public.generations(workspace_id);

create index idx_reviews_generation
on public.reviews(generation_id);

create index idx_reviews_workspace
on public.reviews(workspace_id);

create index idx_chats_workspace
on public.chats(workspace_id);

create index idx_chat_messages_chat
on public.chat_messages(chat_id);

create index idx_notifications_user
on public.notifications(user_id);

create index idx_history_workspace
on public.history(workspace_id);

-- =====================================================
-- HELPER FUNCTIONS
-- =====================================================

create or replace function public.has_role(
    _user_id uuid,
    _role app_role
)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
    select exists (
        select 1
        from public.user_roles
        where user_id = _user_id
          and role = _role
    );
$$;

grant execute on function public.has_role(uuid, app_role)
to authenticated;

create or replace function public.update_updated_at()
returns trigger
language plpgsql
as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

-- =====================================================
-- TRIGGERS
-- =====================================================

create trigger trg_workspaces_updated_at
before update on public.workspaces
for each row
execute function public.update_updated_at();

create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin

    insert into public.profiles (
        id,
        full_name,
        initials,
        avatar_url
    )

    values (

        new.id,

        coalesce(
            new.raw_user_meta_data->>'full_name',
            split_part(new.email, '@', 1)
        ),

        upper(
            left(
                coalesce(
                    new.raw_user_meta_data->>'full_name',
                    split_part(new.email, '@', 1)
                ),
                2
            )
        ),

        null

    );

    return new;

end;
$$;

create or replace function public.assign_default_role()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin

    insert into public.user_roles (

        user_id,
        role

    )

    values (

        new.id,
        'student'

    );

    return new;

end;
$$;

create trigger on_auth_user_created
after insert on auth.users
for each row
execute function public.handle_new_user();

create trigger on_profile_created
after insert on public.profiles
for each row
execute function public.assign_default_role();

-- =====================================================
-- ROW LEVEL SECURITY
-- =====================================================

alter table public.profiles enable row level security;
alter table public.user_roles enable row level security;
alter table public.workspaces enable row level security;
alter table public.documents enable row level security;
alter table public.chunks enable row level security;
alter table public.embeddings enable row level security;
alter table public.generations enable row level security;
alter table public.generation_versions enable row level security;
alter table public.reviews enable row level security;
alter table public.chats enable row level security;
alter table public.chat_messages enable row level security;
alter table public.notifications enable row level security;
alter table public.history enable row level security;
alter table public.analytics enable row level security;

create policy "Users can view their own profile"
on public.profiles
for select
to authenticated
using (id = auth.uid());

create policy "Users can update their own profile"
on public.profiles
for update
to authenticated
using (id = auth.uid());

create policy "Users can insert their own profile"
on public.profiles
for insert
to authenticated
with check (id = auth.uid());

create policy "Users manage their own workspaces"
on public.workspaces
for all
to authenticated
using (owner_id = auth.uid())
with check (owner_id = auth.uid());

create policy "Workspace owners manage documents"
on public.documents
for all
to authenticated
using (
    exists (
        select 1
        from public.workspaces
        where workspaces.id = documents.workspace_id
        and workspaces.owner_id = auth.uid()
    )
)
with check (
    exists (
        select 1
        from public.workspaces
        where workspaces.id = documents.workspace_id
        and workspaces.owner_id = auth.uid()
    )
);

create policy "Workspace owners manage generations"
on public.generations
for all
to authenticated
using (
    exists (
        select 1
        from public.workspaces
        where workspaces.id = generations.workspace_id
        and workspaces.owner_id = auth.uid()
    )
)
with check (
    exists (
        select 1
        from public.workspaces
        where workspaces.id = generations.workspace_id
        and workspaces.owner_id = auth.uid()
    )
);

create policy "Reviewers can manage reviews"
on public.reviews
for all
to authenticated
using (
    public.has_role(auth.uid(), 'reviewer')
    or
    public.has_role(auth.uid(), 'admin')
)
with check (
    public.has_role(auth.uid(), 'reviewer')
    or
    public.has_role(auth.uid(), 'admin')
);

create policy "Users read their own notifications"
on public.notifications
for select
to authenticated
using (
    user_id = auth.uid()
);

-- =====================================================
-- REMAINING RLS POLICIES
-- =====================================================

-- -----------------------------------------------------
-- Chunks
-- -----------------------------------------------------

create policy "Workspace owners manage chunks"
on public.chunks
for all
to authenticated
using (
    exists (
        select 1
        from public.documents d
        join public.workspaces w
            on w.id = d.workspace_id
        where d.id = chunks.document_id
        and w.owner_id = auth.uid()
    )
)
with check (
    exists (
        select 1
        from public.documents d
        join public.workspaces w
            on w.id = d.workspace_id
        where d.id = chunks.document_id
        and w.owner_id = auth.uid()
    )
);

-- -----------------------------------------------------
-- Embeddings
-- -----------------------------------------------------

create policy "Workspace owners manage embeddings"
on public.embeddings
for all
to authenticated
using (
    exists (
        select 1
        from public.chunks c
        join public.documents d
            on d.id = c.document_id
        join public.workspaces w
            on w.id = d.workspace_id
        where c.id = embeddings.chunk_id
        and w.owner_id = auth.uid()
    )
)
with check (
    exists (
        select 1
        from public.chunks c
        join public.documents d
            on d.id = c.document_id
        join public.workspaces w
            on w.id = d.workspace_id
        where c.id = embeddings.chunk_id
        and w.owner_id = auth.uid()
    )
);

-- -----------------------------------------------------
-- Chats
-- -----------------------------------------------------

create policy "Users manage their chats"
on public.chats
for all
to authenticated
using (
    user_id = auth.uid()
)
with check (
    user_id = auth.uid()
);

-- -----------------------------------------------------
-- Chat Messages
-- -----------------------------------------------------

create policy "Users manage their chat messages"
on public.chat_messages
for all
to authenticated
using (
    exists (
        select 1
        from public.chats
        where chats.id = chat_messages.chat_id
        and chats.user_id = auth.uid()
    )
)
with check (
    exists (
        select 1
        from public.chats
        where chats.id = chat_messages.chat_id
        and chats.user_id = auth.uid()
    )
);

-- -----------------------------------------------------
-- History
-- -----------------------------------------------------

create policy "Users manage their history"
on public.history
for all
to authenticated
using (
    user_id = auth.uid()
)
with check (
    user_id = auth.uid()
);

-- -----------------------------------------------------
-- Analytics
-- -----------------------------------------------------

create policy "Workspace owners view analytics"
on public.analytics
for all
to authenticated
using (
    exists (
        select 1
        from public.workspaces
        where workspaces.id = analytics.workspace_id
        and workspaces.owner_id = auth.uid()
    )
)
with check (
    exists (
        select 1
        from public.workspaces
        where workspaces.id = analytics.workspace_id
        and workspaces.owner_id = auth.uid()
    )
);

-- -----------------------------------------------------
-- Generation Versions
-- -----------------------------------------------------

create policy "Workspace owners manage versions"
on public.generation_versions
for all
to authenticated
using (
    exists (
        select 1
        from public.generations g
        join public.workspaces w
            on w.id = g.workspace_id
        where g.id = generation_versions.generation_id
        and w.owner_id = auth.uid()
    )
)
with check (
    exists (
        select 1
        from public.generations g
        join public.workspaces w
            on w.id = g.workspace_id
        where g.id = generation_versions.generation_id
        and w.owner_id = auth.uid()
    )
);