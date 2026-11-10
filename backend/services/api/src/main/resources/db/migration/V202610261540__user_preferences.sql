-- 관심 공고·관심 조건·알림 설정 (user 모듈, 스키마 account. 설계: contracts/schemas/user-preferences.draft.md 2장)
-- 알림 대상자는 이 테이블로 골라요 (UserNotificationQueryService). 소득·자산·나이는 저장하지 않아요 (CLAUDE.md)
-- 탈퇴하면 users 행과 함께 cascade로 지워져요. 웹 푸시 켬·끔은 여기 없어요 (notification.push_subscriptions에 기기가 있으면 켜짐)
-- 이메일(notification_emails)·약관 동의(consents)는 이메일 정리 뒤에 정해요 (지금 운영 채널은 웹 푸시)

-- 관심 공고·관심 정책. 다른 모듈 테이블이라 target_id에 FK를 걸지 않고, 저장할 때 그 모듈 조회 메서드로 있는지 확인해요
create table account.favorites (
    user_id     uuid        not null references account.users (id) on delete cascade,
    target_type varchar(20) not null check (target_type in ('NOTICE', 'BENEFIT', 'SPACE_RECRUITMENT')),
    target_id   uuid        not null,
    created_at  timestamptz not null,
    primary key (user_id, target_type, target_id)
);
create index favorites_target_idx on account.favorites (target_type, target_id);   -- 정정·후속 안내·마감 알림 대상자
create index favorites_user_idx on account.favorites (user_id, created_at desc);   -- 내 관심 목록

-- 지역 코드: 시군구 5자리(11440 마포구), 시도 전체는 xx000(11000 서울 전체). common.regions에 있는 코드만
-- 주거 공고 관심 조건 (NoticePublished field = HOUSING)
create table account.housing_interests (
    user_id            uuid        primary key references account.users (id) on delete cascade,
    region_codes       text[]      not null default '{}',   -- 살고 싶은 곳
    include_nationwide boolean     not null default true,   -- 전국 대상 공고도 받기
    notice_types       text[]      not null default '{}',   -- 공고 유형. 빈 목록 = 전부
    updated_at         timestamptz not null
);

-- 사업공간 공고(BUSINESS_SPACE)·창업지원(STARTUP_SUPPORT)·사업공간 모집(SPACE_RECRUITMENT) 관심 조건
create table account.business_interests (
    user_id            uuid        primary key references account.users (id) on delete cascade,
    region_codes       text[]      not null default '{}',   -- 사업장을 둘(둔) 곳
    include_nationwide boolean     not null default true,
    industry_codes     text[]      not null default '{}',   -- 표준산업분류 대분류 A~U. 빈 목록 = 전부 (v1은 저장만, 정책에 업종 조건이 붙으면 걸러요)
    startup_stages     text[]      not null default '{}',   -- PRE_STARTUP · OPERATING. 빈 목록 = 전부 (v1은 저장만)
    updated_at         timestamptz not null
);

-- 주거·이주 지원 정책 관심 조건 (BenefitPublished field = BENEFIT). 지원 정책은 보통 지금 사는 곳 기준이라 주거 공고 지역과 따로
create table account.support_interests (
    user_id            uuid        primary key references account.users (id) on delete cascade,
    region_codes       text[]      not null default '{}',   -- 혜택 관심 지역 (보통 사는 곳, 시군구까지만)
    include_nationwide boolean     not null default true,
    support_kinds      text[]      not null default '{}',   -- RENT · DEPOSIT_LOAN · PURCHASE_LOAN · HOUSING_SUPPLY · MOVE_IN_GRANT · CASH. 빈 목록 = 전부 (v1은 저장만)
    updated_at         timestamptz not null
);

-- 알림 종류별 켬·끔과 조용한 시간 (웹 푸시·이메일이 같이 써요). 줄이 없는 회원은 모두 켬·조용한 시간 끔으로 봐요
-- 끈 종류도 알림함에는 남아요 (보내지만 않아요)
create table account.notification_settings (
    user_id       uuid        primary key references account.users (id) on delete cascade,
    new_notice    boolean     not null default true,    -- NEW_NOTICE 새 주거·사업공간 공고
    new_support   boolean     not null default true,    -- NEW_SUPPORT 새 지원 정책·창업지원·사업공간 모집
    deadline      boolean     not null default true,    -- DEADLINE_D3·D1 관심 공고 마감
    correction    boolean     not null default true,    -- CORRECTED 관심 공고 정정
    follow_up     boolean     not null default true,    -- FOLLOW_UP 관심 공고 후속 안내
    quiet_enabled boolean     not null default false,   -- 22:00~08:00 알림을 08:00에
    updated_at    timestamptz not null
);
