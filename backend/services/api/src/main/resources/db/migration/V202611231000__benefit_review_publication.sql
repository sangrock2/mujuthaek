create table benefit.review_publications (
    event_id uuid primary key,
    outcome text not null check (outcome in ('PUBLISHED', 'HIDDEN', 'STALE')),
    benefit_id uuid,
    source_version int not null
);
