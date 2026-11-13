create table account.application_preparation_tasks (
    id uuid primary key,
    preparation_id uuid not null references account.application_preparations(id) on delete cascade,
    title varchar(120) not null check (length(btrim(title)) > 0),
    due_on date,
    done boolean not null default false,
    created_at timestamptz not null,
    updated_at timestamptz not null
);
create index application_preparation_tasks_preparation on account.application_preparation_tasks(preparation_id, created_at, id);
