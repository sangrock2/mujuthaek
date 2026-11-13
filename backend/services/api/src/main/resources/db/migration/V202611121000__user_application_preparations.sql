create table account.application_preparations (
    id uuid primary key,
    user_id uuid not null references account.users(id) on delete cascade,
    notice_id uuid not null,
    status text not null default 'PREPARING' check (status in ('PREPARING','SUBMITTED','ARCHIVED')),
    archived_from_status text check (archived_from_status in ('PREPARING','SUBMITTED')),
    submitted_at timestamptz,
    acknowledged_source_revision text not null,
    source_revision text not null,
    source_snapshot jsonb not null,
    acknowledged_snapshot jsonb not null,
    row_version bigint not null default 0,
    merge_review boolean not null default false,
    created_at timestamptz not null,
    updated_at timestamptz not null,
    unique(user_id, notice_id)
);
create table account.application_preparation_aliases (
    id uuid primary key,
    user_id uuid not null references account.users(id) on delete cascade,
    preparation_id uuid not null references account.application_preparations(id) on delete cascade
);
create index application_preparations_user on account.application_preparations(user_id, created_at, id);
create table account.application_preparation_documents (
    preparation_id uuid not null references account.application_preparations(id) on delete cascade,
    source_document_id text not null,
    source_fingerprint text not null,
    state text not null check (state in ('TODO','DONE','NOT_APPLICABLE','CHECK_REQUIRED','RECHECK_REQUIRED')),
    active boolean not null default true,
    updated_at timestamptz not null,
    primary key(preparation_id, source_document_id)
);
