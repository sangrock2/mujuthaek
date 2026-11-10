-- 관리자 권한 (2026-10-27).
--  · 단계: USER / ADMIN(일반 관리자) / SUPER_ADMIN(최상위 관리자, 딱 1명. 화면에서는 만들 수 없고 DB로 정하거나 최상위가 넘겨요)
--  · 일반 관리자는 처음엔 권한이 없고, 받은 권한(admin_permissions)만큼만 관리 화면을 써요. 최상위는 모든 권한을 가진 것으로 봐요(줄을 두지 않음)
--  · 이용 정지(suspensions), 관리자 긴급 정지(admin_freeze: 줄이 있으면 최상위를 뺀 관리자 전원 정지)
--  · 모든 변경은 admin_changes에 한 줄. 대상 회원이 탈퇴하면 그 회원의 기록도 지워요(요구사항 3-16), 바꾼 관리자가 탈퇴하면 누가 바꿨는지만 비워요
alter table account.users drop constraint users_role_check;
alter table account.users add constraint users_role_check check (role in ('USER', 'ADMIN', 'SUPER_ADMIN'));
create unique index users_one_super_admin on account.users (role) where role = 'SUPER_ADMIN';

create table account.admin_permissions (
    user_id     uuid        not null references account.users (id) on delete cascade,
    permission  varchar(30) not null check (permission in (
                    'NOTICE_REVIEW', 'BENEFIT_REVIEW', 'SOURCES', 'CRITERIA', 'REPORTS', 'CHAT',
                    'USERS_VIEW', 'USERS_SUSPEND', 'ADMIN_APPOINT', 'PERMISSION_GRANT', 'PERMISSION_REVOKE',
                    'TRAFFIC', 'ACTIVITY')),
    granted_by  uuid        references account.users (id) on delete set null,
    granted_at  timestamptz not null default now(),
    primary key (user_id, permission)
);

create table account.suspensions (
    user_id       uuid         primary key references account.users (id) on delete cascade,
    reason        varchar(200) not null,
    until         timestamptz,                -- 비우면 해제할 때까지
    suspended_by  uuid         references account.users (id) on delete set null,
    suspended_at  timestamptz  not null default now()
);

create table account.admin_freeze (
    id         boolean      primary key default true check (id),
    reason     varchar(200),
    frozen_by  uuid         references account.users (id) on delete set null,
    frozen_at  timestamptz  not null default now()
);

create table account.admin_changes (
    id          bigint generated always as identity primary key,
    user_id     uuid         references account.users (id) on delete cascade,  -- 긴급 정지는 비움
    kind        varchar(20)  not null check (kind in (
                    'APPOINT', 'DISMISS', 'GRANT', 'REVOKE', 'SUSPEND', 'UNSUSPEND', 'TRANSFER', 'FREEZE', 'UNFREEZE')),
    permission  varchar(30),
    note        varchar(300),
    changed_by  uuid         references account.users (id) on delete set null,
    changed_at  timestamptz  not null default now()
);

create index admin_changes_time_idx on account.admin_changes (changed_at desc);
