# space_recruitments 테이블 (초안 v0)

사업공간 모집 공고(`field = SPACE_RECRUITMENT`)의 AI 추출 결과를 저장하는 api 테이블이에요.
**이벤트 `space-recruitment.extracted` v1의 추출 칸 + 지역**으로 만들어요 (2026-10-22 결정). `benefits`와는 구조가 달라요.

- 저장하는 곳: api DB, 스키마 `benefit`, 모듈 `benefit` (담당자3)
- 받는 이벤트: [`contracts/events/space-recruitment.extracted.v1.json`](../events/space-recruitment.extracted.v1.json) (칸 설명은 [space-recruitment-extracted.draft.md](space-recruitment-extracted.draft.md) 3장)
- 원본: 수집 DB `raw_policies`·`raw_policy_versions` (`field = 'SPACE_RECRUITMENT'`). 수집 칸은 지금으로 충분해서 새로 수집할 칸은 없어요
- 조건 줄의 `type`·`value`는 [benefit-condition-types.draft.md](benefit-condition-types.draft.md)를 따라요
- 상태: **초안**이에요. 확정하면 api 마이그레이션 `V<yyyyMMddHHmm>__benefit_space_recruitments.sql`로 옮겨요

## 1. 테이블 구성

공고 한 건 = `space_recruitments` 1줄 + `space_recruitment_units` 여러 줄 + `space_recruitment_conditions` 여러 줄.

```
space_recruitments (공고 1줄)
 │   relevant·summary, facility, recruitCount, residency, schedule,
 │   selectionMethod·support·howToApply·documents·contact, quality, + 지역
 ├─ space_recruitment_units      (units[]      → 공간 0~N줄)
 └─ space_recruitment_conditions (conditions[] → 입주 자격 0~N줄)
```

이벤트 칸 → 테이블

| 이벤트 칸 | 저장하는 곳 |
| --- | --- |
| `relevant`, `relevanceReason` | `space_recruitments.relevant`, `relevance_reason` |
| `summary` | `space_recruitments.summary` |
| `facility` | `space_recruitments.facility_name`, `facility_kind`, `facility_address`, `facility_evidence` |
| `units[]` | `space_recruitment_units` 여러 줄 |
| `recruitCount` | `space_recruitments.recruit_count` |
| `residency` | `space_recruitments.residency_months`, `extendable_months`, `move_in_date`, `residency_text` |
| `schedule` | `space_recruitments.apply_start`, `apply_end`, `apply_always`, `schedule_text` |
| `selectionMethod`, `support`, `howToApply`, `documents`, `contact` | `space_recruitments`의 같은 이름 칸 |
| `conditions[]` | `space_recruitment_conditions` 여러 줄 |
| `quality` | `space_recruitments.confidence`, `needs_review`, `review_reasons`, `model`, `prompt_version`, `extracted_at` |
| **지역** `source.regionScope`, `regionNames`, `regionCodes` | `space_recruitments.region_scope`, `region_names`, `region_codes` |

지역은 이벤트의 `source`에 이미 있어서 이벤트 계약은 바꾸지 않아요. `regionCodes`가 비어 있으면 extraction이 지역 이름을 코드로 바꿔 채워요.

## 2. `space_recruitments` (공고 한 건)

### 관리 칸 (찾기·버전·화면 연결)

추출 칸은 아니지만, 저장과 화면에 꼭 필요한 칸이에요.

| 칸 | 타입 | 필수 | 뜻 | 채우는 곳 |
| --- | --- | --- | --- | --- |
| `id` | uuid | ✅ | 공고 ID (UUID v7) | benefit이 만듦 |
| `raw_policy_id` | uuid | ✅ 유일 | 수집 DB 정책 ID. 새 버전이 오면 이 값으로 찾아요 | `rawPolicyId` |
| `source_code` | text | ✅ | 출처 (`kstartup`, `bizinfo`, `youth`) | `sourceCode` |
| `source_policy_id` | text | ✅ | 출처의 공고 ID. `source_code`와 함께 유일 | `policyId` |
| `source_version` | int | ✅ | 마지막으로 반영한 수집 버전 (순서 뒤바뀜 대비) | `version` |
| `title` | text | ✅ | 공고 이름 (목록 화면) | `source.title` |
| `detail_url` | text | | 원문 주소 (근거 보기) | `source.detailUrl` |
| `apply_url` | text | | 온라인 신청 주소 | `source.applyUrl` |
| `status` | text | ✅ | `UPCOMING` · `OPEN` · `CLOSED` · `HIDDEN` | benefit이 신청 기간·`relevant`로 계산 |
| `created_at`, `updated_at` | timestamptz | ✅ | 저장·수정 시각 | benefit이 채움 |

### 지역

| 칸 | 타입 | 필수 | 뜻 | 채우는 곳 |
| --- | --- | --- | --- | --- |
| `region_scope` | text | ✅ | `NATIONWIDE` 전국, `SIDO` 시도, `SIGUNGU` 시군구, `UNKNOWN` 모름 | `source.regionScope` |
| `region_names` | text[] | ✅ (빈 목록 가능) | 지역 이름 ('서울', '경상북도 성주군') | `source.regionNames` |
| `region_codes` | text[] | ✅ (빈 목록 가능) | 시도 2자리 / 시군구 5자리 코드. 관심 지역(시군구 5자리) 검색에 써요 | `source.regionCodes` |

### 추출 칸

| 칸 | 타입 | 필수 | 뜻 | 채우는 곳 (이벤트) |
| --- | --- | --- | --- | --- |
| `relevant` | boolean | ✅ | 정말 공간을 빌려주는 모집 공고인지. false면 `status = HIDDEN` | `relevant` |
| `relevance_reason` | text | ✅ | 판단 이유 한 문장 | `relevanceReason` |
| `summary` | text | | 한 줄 요약 (80자 안) | `summary` |
| `facility_name` | text | | 시설 이름 ('서울창업센터 동작') | `facility.name` |
| `facility_kind` | text | ✅ | `INCUBATOR` 창업보육센터·창업센터, `SHARED_OFFICE` 공유오피스, `OFFICE` 사무실·업무시설, `FACTORY` 공장·제조공간, `OTHER` | `facility.kind` |
| `facility_address` | text | | 시설 주소 원문 | `facility.address` |
| `facility_evidence` | text | | 시설 이름·주소가 들어 있는 원문 문장 | `facility.evidence` |
| `recruit_count` | int | | 모집 기업·팀 수 | `recruitCount` |
| `residency_months` | int | | 기본 입주 기간 (개월) | `residency.months` |
| `extendable_months` | int | | 연장 포함 최대 기간 (개월) | `residency.extendableMonths` |
| `move_in_date` | date | | 입주 예정일 | `residency.moveInDate` |
| `residency_text` | text | | 입주 기간 원문 | `residency.rawText` |
| `hq_relocation_required` | boolean | | 입주 후 본점 이전 필수인지 (null 글에 없음). 판정하지 않고 화면에만 보여요 | `hqRelocation.mandatory` |
| `hq_relocation_months` | int | | 본점 이전 기한 (개월) | `hqRelocation.withinMonths` |
| `hq_relocation_text` | text | | 본점 이전 원문 | `hqRelocation.rawText` |
| `apply_start`, `apply_end` | date | | 신청 시작일·마감일 | `schedule.applyStart`·`applyEnd` |
| `apply_always` | boolean | ✅ (기본 false) | 상시 모집 ('공실 발생 시 수시 모집') | `schedule.applyAlways` |
| `schedule_text` | text | | 신청 기간 원문 | `schedule.rawText` |
| `selection_method` | text | | 선정 방법 요약 | `selectionMethod` |
| `support` | text[] | ✅ (빈 목록 가능) | 입주하면 함께 받는 지원 (멘토링, 투자 연계 …) | `support` |
| `how_to_apply` | text | | 신청 방법 요약 | `howToApply` |
| `documents` | text[] | ✅ (빈 목록 가능) | 제출 서류 | `documents` |
| `contact` | text | | 문의처 | `contact` |
| `confidence` | numeric(3,2) | | 공고 전체 신뢰도 0~1 | `quality.confidence` |
| `needs_review` | boolean | ✅ (기본 false) | 사람 확인 필요 | `quality.needsReview` |
| `review_reasons` | text[] | ✅ (빈 목록 가능) | 확인 이유 (`EVIDENCE_NOT_FOUND`, `LOW_CONFIDENCE`, `NO_DOCUMENT`, `RULE_AI_CONFLICT`, `TEXT_TRUNCATED`) | `quality.reviewReasons` |
| `model` | text | ✅ | 추출에 쓴 모델 (다시 추출할 대상을 고를 때) | `quality.model` |
| `prompt_version` | text | ✅ | 프롬프트 버전 | `quality.promptVersion` |
| `extracted_at` | timestamptz | ✅ | 추출 시각 | `quality.extractedAt` |

인덱스: `(status, apply_end)` 목록·마감 임박, `region_codes` GIN 지역 검색, `facility_kind` 공간 종류 필터.

## 3. `space_recruitment_units` (공간, 공고당 0~N줄)

종류·크기·임대료가 다른 공간마다 한 줄이에요. 글에 공간 정보가 없으면 줄이 없어요.

| 칸 | 타입 | 필수 | 뜻 | 채우는 곳 (`units[]`) |
| --- | --- | --- | --- | --- |
| `id` | uuid | ✅ | 줄 ID | benefit이 만듦 |
| `space_recruitment_id` | uuid | ✅ | `space_recruitments.id` (공고가 지워지면 같이 지워짐) | |
| `ordinal` | int | ✅ | 순서 (배열 순서) | |
| `name` | text | | 공간 이름 ('1인실', 'A동 201호') | `name` |
| `unit_count` | int | | 호실·좌석 수 | `count` |
| `area_m2` | numeric(8,2) | | 전용 면적 (㎡) | `areaM2` |
| `seats` | int | | 한 공간의 좌석·인원 수 | `seats` |
| `deposit` | bigint | | 보증금 (원) | `deposit` |
| `monthly_rent` | bigint | | 월 임대료 (원). 무상이면 0 | `monthlyRent` |
| `maintenance_fee` | bigint | | 월 관리비 (원) | `maintenanceFee` |
| `raw_text` | text | ✅ | 원문 | `rawText` |
| `evidence` | text | ✅ | 원문이 들어 있는 문장 | `evidence` |

금액은 **원** 단위예요. 관리비·소액 임대료가 만 원 아래로 자주 나와서예요.
칸으로 두니까 "임대료 무상", "면적 10㎡ 이상", "관리비 5만 원 이하", "보증금 없음" 같은 필터를 쓸 수 있어요.

## 4. `space_recruitment_conditions` (입주 자격, 공고당 0~N줄)

조건 한 줄의 모양은 지원 정책(`benefit_conditions`)과 같아요. 조건 줄이 없으면 "제한 없음"이에요.

| 칸 | 타입 | 필수 | 뜻 | 채우는 곳 (`conditions[]`) |
| --- | --- | --- | --- | --- |
| `id` | uuid | ✅ | 줄 ID | benefit이 만듦 |
| `space_recruitment_id` | uuid | ✅ | `space_recruitments.id` (공고가 지워지면 같이 지워짐) | |
| `ordinal` | int | ✅ | 순서 (배열 순서) | |
| `type` | text | ✅ | 조건 종류 | `type` |
| `value` | jsonb | | type마다 정해진 값. `known=false`면 null | `value` |
| `grp` | int | ✅ | 같은 번호 "또는", 다른 번호 "그리고" | `group` |
| `known` | boolean | ✅ | 값으로 바꿨는지 (false면 판정 UNKNOWN) | `known` |
| `raw_text` | text | ✅ | 조건 원문 (화면의 판정 근거) | `rawText` |
| `evidence` | text | ✅ | 원문이 들어 있는 문장 | `evidence` |
| `confidence` | numeric(3,2) | ✅ | 신뢰도 0~1 (규칙이면 1) | `confidence` |
| `origin` | text | ✅ | `RULE` (출처 코드 칸) · `AI` (글) | `origin` |

사업공간 모집에서 주로 나오는 type (condition-types 3-5)

| type | 예 |
| --- | --- |
| `STARTUP_STAGE` | "예비창업자 또는 창업 후 기업" → `{"in":["PRE_STARTUP","OPERATING"]}` |
| `BUSINESS_YEARS` | "창업 3년 이내" → `{"max":3}` |
| `INDUSTRY` | "정보통신·제조 분야" → `{"in":["J","C"]}` |
| `BUSINESS_LOCATION` | "서울 소재 기업" (신청할 때의 사업장) → `{"regions":["11"]}`. 입주 후 본점 이전 의무는 조건이 아니라 `hq_relocation_*` 칸이에요 |
| `AGE` | "대표자 만 39세 이하" → `{"max":39}` |
| `EXCLUSIVE` · `PRIORITY` · `OTHER` | 제외 대상, 우대 사항, 값으로 못 바꾼 조건 (글만 보여줌) |

인덱스: `space_recruitment_id`, `type`.

## 5. SQL (초안)

```sql
create table benefit.space_recruitments (
    id                 uuid primary key,                 -- UUID v7

    -- 관리 칸
    raw_policy_id      uuid        not null unique,      -- 수집 DB 정책 ID (이벤트 키)
    source_code        text        not null,             -- kstartup, bizinfo, youth
    source_policy_id   text        not null,
    source_version     int         not null,             -- 마지막으로 반영한 수집 버전
    title              text        not null,
    detail_url         text,
    apply_url          text,
    status             text        not null,             -- UPCOMING, OPEN, CLOSED, HIDDEN

    -- 지역
    region_scope       text        not null,             -- NATIONWIDE, SIDO, SIGUNGU, UNKNOWN
    region_names       text[]      not null default '{}',
    region_codes       text[]      not null default '{}', -- 시도 2자리 / 시군구 5자리

    -- 추출 칸
    relevant           boolean     not null,
    relevance_reason   text        not null,
    summary            text,
    facility_name      text,
    facility_kind      text        not null,             -- INCUBATOR, SHARED_OFFICE, OFFICE, FACTORY, OTHER
    facility_address   text,
    facility_evidence  text,
    recruit_count      int,
    residency_months   int,
    extendable_months  int,
    move_in_date       date,
    residency_text     text,
    hq_relocation_required boolean,
    hq_relocation_months   int,
    hq_relocation_text     text,
    apply_start        date,
    apply_end          date,
    apply_always       boolean     not null default false,
    schedule_text      text,
    selection_method   text,
    support            text[]      not null default '{}',
    how_to_apply       text,
    documents          text[]      not null default '{}',
    contact            text,

    -- 신뢰도
    confidence         numeric(3,2),
    needs_review       boolean     not null default false,
    review_reasons     text[]      not null default '{}',
    model              text        not null,
    prompt_version     text        not null,
    extracted_at       timestamptz not null,

    created_at         timestamptz not null default now(),
    updated_at         timestamptz not null default now(),
    unique (source_code, source_policy_id)
);
create index space_recruitments_open_idx on benefit.space_recruitments (status, apply_end);
create index space_recruitments_region_idx on benefit.space_recruitments using gin (region_codes);
create index space_recruitments_kind_idx on benefit.space_recruitments (facility_kind);

create table benefit.space_recruitment_units (
    id                    uuid primary key,
    space_recruitment_id  uuid not null references benefit.space_recruitments (id) on delete cascade,
    ordinal               int  not null,
    name                  text,
    unit_count            int,
    area_m2               numeric(8,2),
    seats                 int,
    deposit               bigint,                        -- 원
    monthly_rent          bigint,                        -- 원, 무상이면 0
    maintenance_fee       bigint,                        -- 원
    raw_text              text not null,
    evidence              text not null
);
create index space_recruitment_units_parent_idx on benefit.space_recruitment_units (space_recruitment_id);

create table benefit.space_recruitment_conditions (
    id                    uuid primary key,
    space_recruitment_id  uuid not null references benefit.space_recruitments (id) on delete cascade,
    ordinal               int  not null,
    type                  text not null,                 -- condition-types 3장
    value                 jsonb,                         -- known=false면 null
    grp                   int  not null,                 -- 같은 번호 "또는", 다른 번호 "그리고"
    known                 boolean not null,
    raw_text              text not null,
    evidence              text not null,
    confidence            numeric(3,2) not null,
    origin                text not null                  -- RULE, AI
);
create index space_recruitment_conditions_parent_idx on benefit.space_recruitment_conditions (space_recruitment_id);
create index space_recruitment_conditions_type_idx on benefit.space_recruitment_conditions (type);
```

## 6. 저장 규칙

| 상황 | 하는 일 |
| --- | --- |
| 처음 받은 `rawPolicyId` | `space_recruitments` 추가 + 공간·조건 줄 추가 |
| 이미 있는 `rawPolicyId`, 더 큰 `version` | 공고 줄을 고치고 공간·조건 줄은 **지우고 다시 넣어요** (줄 단위 비교 안 함) |
| 같거나 작은 `version` | 버려요 (같은 이벤트 두 번은 `common.processed_events`로 막아요) |
| `relevant=false` | `status = HIDDEN`. 목록에서 빼요 |
| 매일 상태 갱신 | `apply_start` 전 `UPCOMING`, 기간 안이거나 `apply_always` `OPEN`, `apply_end` 지나면 `CLOSED` |
| 분류가 바뀐 공고 | 수집기가 같은 `rawPolicyId`를 다른 분류로 다시 보내면, 새 분류의 테이블에 넣고 다른 테이블(`benefits`)의 줄은 지워요 |

- 수집 DB 테이블은 읽지 않아요. 필요한 건 모두 이벤트에 있어요
- 원문 `text`·`record`는 저장하지 않아요. 원문은 `detail_url`로, 근거는 `raw_text`·`evidence`로 보여줘요
- 사용자 정보(소득·자산·나이)는 이 테이블에 없어요

## 7. 결정이 필요한 것

1. **관리 칸**: `title`·`detail_url`·`apply_url`·`status`는 이벤트 추출 칸이 아니지만 목록 화면과 근거 보기에 필요해서 넣었어요. 기관(`agency`)·출처 분야(`categories`)도 화면에 보여줄지
2. **관심 공고·알림**: 관심 공고(요구사항 3-12)에 사업공간 모집도 넣을지. 넣으면 관심 공고 테이블이 `benefits`·`space_recruitments` 둘을 가리킬 수 있어야 해요
3. **판정**: 입주 자격을 eligibility가 판정할지 (조건 줄 모양이 `benefit_conditions`와 같아서 판정 코드를 함께 쓸 수 있어요)
