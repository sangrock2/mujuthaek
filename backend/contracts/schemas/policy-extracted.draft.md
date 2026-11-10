# 정책 추출 결과 계약 · benefits 테이블 (초안 v0)

정책 API 수집(`raw.policy.collected`) → AI 추출(extraction) → benefit 모듈 저장까지의 약속이에요.

- 보내는 쪽: extraction `rules/policy`·`rules/startup_support` (담당자3), 공통 추출·검증 코드 (담당자2)
- 받는 쪽: api `benefit` 모듈 (담당자3). eligibility는 benefit의 service 조회 메서드로 조건을 읽어요
- 조건 한 줄의 모양과 type 목록은 [benefit-condition-types.draft.md](benefit-condition-types.draft.md)를 따라요
- 대상은 **지원 정책**(`field` = `BENEFIT`·`STARTUP_SUPPORT`)이에요. 사업공간 모집(`SPACE_RECRUITMENT`)은 [space-recruitment-extracted.draft.md](space-recruitment-extracted.draft.md)의 `space_recruitments`에 저장해요 (2026-10-22 결정)
- 상태: **초안**이에요. 담당자2(extraction)·담당자4(eligibility) 확인 후 `contracts/events/policy.extracted.v1.json`과 api 마이그레이션으로 옮겨요

## 1. 흐름

```
collector ──raw.policy.collected──▶ extraction ──policy.extracted──▶ api benefit
 (원본 + 통일 기본 칸)                (AI 추출 + 규칙 매핑 + 검증)        (benefits 저장 → BenefitPublished)
```

| 단계 | 하는 일 |
| --- | --- |
| extraction | `text`를 AI에 넣어 관련성·조건·지원 내용·일정을 뽑아요. `record`의 코드 칸(온통청년 코드, 보조금24 `JA` 코드, 나이 칸)은 규칙으로 옮겨요. 규칙 값이 AI 값보다 우선이에요. `evidence`가 `text`에 그대로 있는지 검증해요 |
| api benefit | 이벤트를 받아 `benefits` 한 줄 + 조건·지원 내용 여러 줄로 저장해요. 통일 기본 칸(제목·기관·지역·주소)은 받은 그대로 써요. 자격 판정은 하지 않아요 (eligibility가 해요) |

## 2. 이벤트 `policy.extracted` v1

봉투(`eventId`, `eventType`, `schemaVersion`, `occurredAt`, `producer: "extraction"`)는 다른 이벤트와 같아요. `raw.policy.collected` 한 건마다 한 건을 보내요.

### payload

| 칸 | 모양 | 뜻 | 누가 채움 |
| --- | --- | --- | --- |
| `rawPolicyId` | uuid | 수집 DB의 정책 ID. benefits를 찾는 키 | 받은 그대로 |
| `version` | int | 수집 버전. 받는 쪽은 저장된 버전보다 작으면 버려요 (순서 뒤바뀜 대비) | 받은 그대로 |
| `sourceCode`, `provider`, `policyId` | string | 출처와 출처 정책 ID | 받은 그대로 |
| `field` | `BENEFIT` · `STARTUP_SUPPORT` | 분야 (`SPACE_RECRUITMENT`는 이 이벤트로 오지 않아요) | 받은 그대로 |
| `reprocess` | bool | true면 사용자 알림을 보내지 않아요 | 받은 그대로 |
| `source` | object | 통일 기본 칸 (3-1) | 받은 그대로 |
| `relevant` | bool | 서비스 범위에 맞는지 (이주 혜택, 창업 공간·자금). false면 benefit은 숨겨요 | AI |
| `relevanceReason` | string | 판단 이유 한 문장 | AI |
| `summary` | string \| null | 화면에 보일 한 줄 요약 (80자 안) | AI |
| `supports` | array | 지원 내용 (3-2) | AI |
| `schedule` | object | 신청·사업 기간 (3-3) | 규칙 → 없으면 AI |
| `howToApply` | string \| null | 신청 방법 요약 | AI |
| `documents` | string[] | 제출 서류 이름 | AI |
| `contact` | string \| null | 문의처 | AI |
| `conditions` | array | 자격 조건 ([condition-types](benefit-condition-types.draft.md) 1장 모양 + `origin`) | 규칙 + AI |
| `quality` | object | 신뢰도 정보 (3-4) | extraction |

`relevant=false`여도 다른 칸은 채워서 보내요. 사람이 확인할 때 쓰고, 범위 판단이 틀렸을 때 다시 추출하지 않아도 돼요.

### 3-1. `source` (수집기가 통일한 기본 칸, 그대로 전달)

```json
{
  "title": "청년 취업자 주거비 지원사업",
  "agency": "전북특별자치도 무주군",
  "regionScope": "SIGUNGU",
  "regionNames": ["전북특별자치도 무주군"],
  "regionCodes": ["52730"],
  "categories": ["주거", "전월세 및 주거급여 지원"],
  "detailUrl": "https://www.youthcenter.go.kr/...",
  "applyUrl": null
}
```

`regionCodes`가 비어 있고 `regionNames`만 있으면 extraction이 지역 이름을 코드로 바꿔 채워요 (6장 1번).

### 3-2. `supports[]` (지원 내용)

| 칸 | 모양 | 뜻 |
| --- | --- | --- |
| `kind` | enum | 아래 표 |
| `amountMax` | int \| null | 최대 금액 (만 원). 금액이 없거나 못 읽으면 null |
| `amountPer` | `ONCE` · `MONTH` · `YEAR` \| null | 금액 단위 기간 |
| `months` | int \| null | 지원 기간 (개월) |
| `ratePct` | number | null | 지원 비율 (이자·임대료의 50%면 50, 「연 3.5%」면 3.5) |\| null | 지원 비율 (이자·임대료의 50%면 50) |
| `rawText` | string | 원문 |
| `evidence` | string | 원문이 들어 있는 문장 (`text`에 그대로 있어야 해요) |

| kind | 뜻 | 분야 |
| --- | --- | --- |
| `RENT` | 월세·임대료 지원 | 혜택 |
| `DEPOSIT_LOAN` | 전·월세 보증금 대출, 이자 지원 | 혜택 |
| `PURCHASE_LOAN` | 주택 구입 대출, 이자 지원 | 혜택 |
| `HOUSING_SUPPLY` | 임대주택·빈집 등 집 자체 제공 | 혜택 |
| `MOVE_IN_GRANT` | 전입·정착·이사 지원금 | 혜택 |
| `CASH` | 그 밖의 현금 지원 | 공통 |
| `GRANT` | 사업화 자금 (갚지 않음) | 창업 |
| `LOAN` | 융자·보증·정책자금 (갚음) | 창업 |
| `SPACE` | 사무실·입주 공간·보육센터 | 창업 |
| `OTHER` | 위에 없는 지원 (교육·상담 등이 같이 있을 때) | 공통 |

### 3-3. `schedule`

```json
{
  "applyStart": "2026-01-23",
  "applyEnd": "2026-02-02",
  "applyAlways": false,
  "businessStart": "2026-01-01",
  "businessEnd": "2026-12-31",
  "rawText": "20260123 ~ 20260202"
}
```

- 날짜는 `YYYY-MM-DD`. 모르면 null
- `applyAlways`: 상시 모집 (온통청년 신청 기간 구분 상시, "예산 소진 시까지" 등)
- 출처에 날짜 칸이 있으면 규칙으로 바꿔요 (온통청년 `aplyYmd`, K-Startup `pbanc_rcpt_*_dt`, 기업마당 `reqstBeginEndDe`). 보조금24·복지로처럼 글만 있으면 AI가 읽어요

### 3-4. `quality`

| 칸 | 뜻 |
| --- | --- |
| `confidence` | 정책 전체 신뢰도 0~1. `hasDocument=false`이고 "공고문 참조"뿐이면 낮아요 |
| `needsReview` | 사람이 확인해야 하는지. 검증 실패(evidence가 원문에 없음), `confidence` 0.6 미만, `relevant` 판단이 애매함 |
| `reviewed` | 사람이 검수해 승인·반려한 결과인지 (선택, 없으면 false). 검수 결과는 검수 전 결과와 같은 `version`으로 다시 나가요 |
| `reviewReasons` | `EVIDENCE_NOT_FOUND`, `LOW_CONFIDENCE`, `NO_DOCUMENT`, `RULE_AI_CONFLICT`, `TEXT_TRUNCATED` |
| `hasDocument`, `documentStatus` | 수집 이벤트 값 그대로 |
| `model`, `promptVersion` | 추출에 쓴 모델·프롬프트 버전 (다시 추출할 대상을 고를 때) |
| `extractedAt` | 추출 시각 |

### 3-5. `conditions[]`

[condition-types](benefit-condition-types.draft.md) 1장 모양에 `origin` 하나를 더해요.

| 칸 | 뜻 |
| --- | --- |
| `origin` | `RULE` (출처 코드 칸에서 규칙으로) · `AI` (글에서 AI가) |

같은 type이 규칙과 AI 둘 다에서 나오면 규칙 줄만 보내고, 값이 다르면 `quality.reviewReasons`에 `RULE_AI_CONFLICT`를 넣어요.

## 4. benefits 테이블 (api DB, 스키마 `benefit`)

정책 한 건 = `benefits` 1줄 + `benefit_supports` 여러 줄 + `benefit_conditions` 여러 줄. 아래 둘은 `benefit_id`로 `benefits`에 붙어요.

```
benefits (정책 1줄)
 ├─ benefit_supports   (지원 내용 0~N줄)
 └─ benefit_conditions (자격 조건 0~N줄, 값 규칙은 benefit-condition-types.draft.md)
```

### `benefits` (정책 한 건)

| 칸 | 타입 | 필수 | 뜻 | 채우는 곳 (이벤트 칸) |
| --- | --- | --- | --- | --- |
| `id` | uuid | ✅ | 정책 ID (UUID v7) | benefit이 만듦 |
| `raw_policy_id` | uuid | ✅ 유일 | 수집 DB 정책 ID. 새 버전이 오면 이 값으로 찾아요 | `rawPolicyId` |
| `source_code` | text | ✅ | 출처 (`gov24`, `bokjiro_central`, `bokjiro_local`, `youth`, `kstartup`, `bizinfo`) | `sourceCode` |
| `provider` | text | ✅ | API 제공처 (`GOV24`, `BOKJIRO`, `YOUTHCENTER`, `KSTARTUP`, `BIZINFO`) | `provider` |
| `source_policy_id` | text | ✅ | 출처의 정책 ID. `source_code`와 함께 유일 | `policyId` |
| `source_version` | int | ✅ | 마지막으로 반영한 수집 버전 | `version` |
| `field` | text | ✅ | `BENEFIT` · `STARTUP_SUPPORT` | `field` |
| `title` | text | ✅ | 정책 이름 | `source.title` |
| `agency` | text | | 소관·주관 기관 | `source.agency` |
| `region_scope` | text | ✅ | `NATIONWIDE` · `SIDO` · `SIGUNGU` · `UNKNOWN` | `source.regionScope` |
| `region_names` | text[] | ✅ (빈 목록 가능) | 지역 이름 | `source.regionNames` |
| `region_codes` | text[] | ✅ (빈 목록 가능) | 시도 2자리 / 시군구 5자리 코드 | `source.regionCodes` |
| `categories` | text[] | ✅ (빈 목록 가능) | 출처가 붙인 분야 | `source.categories` |
| `detail_url` | text | | 원문 주소 | `source.detailUrl` |
| `apply_url` | text | | 온라인 신청 주소 | `source.applyUrl` |
| `summary` | text | | 한 줄 요약 (80자 안) | `summary` (AI) |
| `apply_start`, `apply_end` | date | | 신청 시작일·마감일 | `schedule.applyStart`·`applyEnd` |
| `apply_always` | boolean | ✅ (기본 false) | 상시 모집 | `schedule.applyAlways` |
| `business_start`, `business_end` | date | | 사업 기간 | `schedule.businessStart`·`businessEnd` |
| `schedule_text` | text | | 기간 원문 ("예산 소진 시까지" 등) | `schedule.rawText` |
| `how_to_apply` | text | | 신청 방법 요약 | `howToApply` (AI) |
| `documents` | text[] | ✅ (빈 목록 가능) | 제출 서류 | `documents` (AI) |
| `contact` | text | | 문의처 | `contact` (AI) |
| `status` | text | ✅ | `UPCOMING` · `OPEN` · `CLOSED` · `HIDDEN` | benefit이 날짜·`relevant`로 계산 |
| `relevant` | boolean | ✅ | 서비스 범위에 맞는지. false면 `HIDDEN` | `relevant` (AI) |
| `confidence` | numeric(3,2) | | 정책 전체 신뢰도 0~1 | `quality.confidence` |
| `needs_review` | boolean | ✅ (기본 false) | 사람 확인 필요 | `quality.needsReview` |
| `review_reasons` | text[] | ✅ (빈 목록 가능) | 확인 이유 (`EVIDENCE_NOT_FOUND` 등) | `quality.reviewReasons` |
| `has_document` | boolean | ✅ | 공고문 글자로 추출했는지 | `quality.hasDocument` |
| `extracted_at` | timestamptz | ✅ | 추출 시각 | `quality.extractedAt` |
| `created_at`, `updated_at` | timestamptz | ✅ | 저장·수정 시각 | benefit이 채움 |

인덱스: `(field, status, apply_end)` 목록 조회, `region_codes` GIN 지역 검색.

### `benefit_supports` (지원 내용, 정책당 0~N줄)

| 칸 | 타입 | 필수 | 뜻 | 채우는 곳 (`supports[]`) |
| --- | --- | --- | --- | --- |
| `id` | uuid | ✅ | 줄 ID | benefit이 만듦 |
| `benefit_id` | uuid | ✅ | `benefits.id` (정책이 지워지면 같이 지워짐) | |
| `ordinal` | int | ✅ | 순서 (배열 순서) | |
| `kind` | text | ✅ | `RENT`, `DEPOSIT_LOAN`, `PURCHASE_LOAN`, `HOUSING_SUPPLY`, `MOVE_IN_GRANT`, `CASH`, `GRANT`, `LOAN`, `SPACE`, `OTHER` (3-2) | `kind` |
| `amount_max` | int | | 최대 금액 (만 원) | `amountMax` |
| `amount_per` | text | | `ONCE` · `MONTH` · `YEAR` | `amountPer` |
| `months` | int | | 지원 기간 (개월) | `months` |
| `rate_pct` | numeric(5,2) | | 지원 비율 (%) | `ratePct` |
| `raw_text` | text | ✅ | 원문 | `rawText` |
| `evidence` | text | ✅ | 원문이 들어 있는 문장 | `evidence` |

### `benefit_conditions` (자격 조건, 정책당 0~N줄)

`type`·`value`에 넣을 값은 [benefit-condition-types.draft.md](benefit-condition-types.draft.md)를 따라요. 조건 줄이 없으면 "제한 없음"이에요.

| 칸 | 타입 | 필수 | 뜻 | 채우는 곳 (`conditions[]`) |
| --- | --- | --- | --- | --- |
| `id` | uuid | ✅ | 줄 ID | benefit이 만듦 |
| `benefit_id` | uuid | ✅ | `benefits.id` (정책이 지워지면 같이 지워짐) | |
| `ordinal` | int | ✅ | 순서 (배열 순서) | |
| `type` | text | ✅ | 조건 종류 (`AGE`, `INCOME_MEDIAN_PCT`, `MOVE_IN` …) | `type` |
| `value` | jsonb | | type마다 정해진 값 (`{"min":19,"max":39}`). `known=false`면 null | `value` |
| `grp` | int | ✅ | 같은 번호 "또는", 다른 번호 "그리고" | `group` |
| `known` | boolean | ✅ | 값으로 바꿨는지 (false면 판정 UNKNOWN) | `known` |
| `raw_text` | text | ✅ | 조건 원문 (화면의 판정 근거) | `rawText` |
| `evidence` | text | ✅ | 원문이 들어 있는 문장 | `evidence` |
| `confidence` | numeric(3,2) | ✅ | 신뢰도 0~1 (규칙이면 1) | `confidence` |
| `origin` | text | ✅ | `RULE` (출처 코드 칸) · `AI` (글) | `origin` |

인덱스: `benefit_id`, `type` ("소득 조건이 있는 정책" 같은 조회).

### SQL (초안)

```sql
create table benefit.benefits (
    id                uuid primary key,                 -- UUID v7
    raw_policy_id     uuid        not null unique,      -- 수집 DB 정책 ID (이벤트 키)
    source_code       text        not null,
    provider          text        not null,
    source_policy_id  text        not null,
    source_version    int         not null,             -- 마지막으로 반영한 수집 버전
    field             text        not null,             -- BENEFIT, STARTUP_SUPPORT

    -- 통일 기본 칸 (이벤트 source 그대로)
    title             text        not null,
    agency            text,
    region_scope      text        not null,             -- NATIONWIDE, SIDO, SIGUNGU, UNKNOWN
    region_names      text[]      not null default '{}',
    region_codes      text[]      not null default '{}', -- 시도 2자리 / 시군구 5자리
    categories        text[]      not null default '{}',
    detail_url        text,
    apply_url         text,

    -- AI·규칙 추출
    summary           text,
    apply_start       date,
    apply_end         date,
    apply_always      boolean     not null default false,
    business_start    date,
    business_end      date,
    schedule_text     text,
    how_to_apply      text,
    documents         text[]      not null default '{}',
    contact           text,

    -- 상태·신뢰도
    status            text        not null,             -- UPCOMING, OPEN, CLOSED, HIDDEN
    relevant          boolean     not null,
    confidence        numeric(3,2),
    needs_review      boolean     not null default false,
    review_reasons    text[]      not null default '{}',
    has_document      boolean     not null,
    extracted_at      timestamptz not null,
    created_at        timestamptz not null default now(),
    updated_at        timestamptz not null default now(),

    unique (source_code, source_policy_id)
);
create index benefits_open_idx on benefit.benefits (field, status, apply_end);
create index benefits_region_idx on benefit.benefits using gin (region_codes);

create table benefit.benefit_supports (
    id          uuid primary key,
    benefit_id  uuid not null references benefit.benefits (id) on delete cascade,
    ordinal     int  not null,
    kind        text not null,
    amount_max  int,                                    -- 만 원
    amount_per  text,                                   -- ONCE, MONTH, YEAR
    months      int,
    rate_pct    numeric(5, 2),
    raw_text    text not null,
    evidence    text not null
);
create index benefit_supports_benefit_idx on benefit.benefit_supports (benefit_id);

create table benefit.benefit_conditions (
    id          uuid primary key,
    benefit_id  uuid not null references benefit.benefits (id) on delete cascade,
    ordinal     int  not null,
    type        text not null,                          -- condition-types 3장
    value       jsonb,                                  -- known=false면 null
    grp         int  not null,                          -- 같은 번호 "또는", 다른 번호 "그리고"
    known       boolean not null,
    raw_text    text not null,
    evidence    text not null,
    confidence  numeric(3,2) not null,
    origin      text not null                           -- RULE, AI
);
create index benefit_conditions_benefit_idx on benefit.benefit_conditions (benefit_id);
create index benefit_conditions_type_idx on benefit.benefit_conditions (type);
```

### 저장 규칙

| 상황 | 하는 일 |
| --- | --- |
| 처음 받은 `rawPolicyId` | `benefits` 추가 + 지원·조건 줄 추가. `relevant`이고 `reprocess=false`면 `BenefitPublished(benefitId, field, regionScope, regionCodes, title, reprocess)` (지역은 저장한 값 전부) |
| 이미 있는 `rawPolicyId`, 더 큰 `version` | `benefits` 고치고 지원·조건 줄은 **지우고 다시 넣어요** (줄 단위 비교 안 함) |
| └ 숨김(`relevant=false`)이던 정책이 `relevant`가 됨 | 처음 보이는 것과 같아서 `BenefitPublished` (`reprocess=false`일 때) |
| └ 보이던 정책이 계속 `relevant` | 고치기 전 값과 비교해 사용자가 볼 내용이 바뀌었으면 `BenefitUpdated(benefitId, field, version, changedFields, reprocess)`. `changedFields`: `basic`(제목·기관) · `region` · `schedule`(신청·사업 기간) · `supports`(종류·금액·단위·개월·비율) · `conditions`(종류·값·묶음·known) · `application`(서류·문의처·신청 주소). **AI 글(요약·신청 방법·일정 원문·근거·원문 글자)과 신뢰도는 비교하지 않아요** (재추출할 때마다 정정 알림이 가지 않게). 재처리면 `reprocess=true`로 보내요 (알림은 안 보냄) |
| 같은 `version`의 검수 결과(`quality.reviewed=true`) | 더 큰 버전처럼 고쳐요 (승인·반려가 검수 전 결과를 바꿔요). 검수 결과는 `reprocess=true`라 바뀜 알림은 재처리 표시로 가요 |
| 같거나 작은 `version` (검수 결과가 아님) | 버려요 (같은 이벤트 두 번은 `common.processed_events`로 막아요). 같은 버전의 검수 결과도 이걸로 덮지 않아요 |
| `relevant=false` | `status = HIDDEN`. 목록·판정에서 빼요 |
| 매일 상태 갱신 | `apply_start` 전 `UPCOMING`, 기간 안이거나 `apply_always` `OPEN`, `apply_end` 지나면 `CLOSED` + `BenefitClosed` |

- 수집 DB 테이블은 읽지 않아요. 필요한 건 모두 이벤트에 있어요
- 원문 `text`·`record`는 저장하지 않아요. 원문은 `detail_url`로 보여주고, 근거는 `raw_text`·`evidence`로 보여줘요
- 사용자 정보(소득·자산·나이)는 이 테이블에 없어요. 판정 결과도 eligibility가 따로 가져요

### 통일 칸이 어디로 가는지

| 수집 DB 칸 | benefits 칸 | 비고 |
| --- | --- | --- |
| 제목·기관·지역·분야·주소 | 같은 이름 칸 | 이벤트 `source`로 그대로 |
| `target`, `criteria` (대상·선정기준 글) | `benefit_conditions` | AI가 조건 줄로 나눠요 |
| `benefit` (지원 내용 글) | `benefit_supports` | AI가 금액·기간으로 나눠요 |
| `apply_period` | `apply_start`·`apply_end`·`schedule_text` | 규칙 또는 AI가 날짜로 |
| `how_to_apply`, `documents` | 같은 이름 칸 | AI가 요약 |
| `age_min`·`age_max` | `benefit_conditions` `AGE` 줄 | 규칙 (`origin=RULE`) |

수집 DB의 내용 칸은 글이고, benefits는 판정할 수 있는 값이에요. 그래서 내용 칸은 이벤트에 넣지 않고 AI가 원본에서 다시 뽑아요.

## 5. 예시 (실제 수집 데이터: 온통청년 "청년 취업자 주거비 지원사업")

### 받은 원본 (`text` 일부)
```
정책명: 청년 취업자 주거비 지원사업
취업 상태: 0013001,0013002,0013004,0013005,0013009
법정 시군구 코드: 52730
신청 기간: 20260123 ~ 20260202
소득 기타 조건: 가구 기준중위소득 180% 이하
지원 내용: 무주군에 거주하며 취업중인 청년에게 주거비 지원
정책 설명: 월 임대료 또는 전세 대출 이자 50%를 월 최대 20만원까지 12개월간 지원
참여 제한 대상: 주거급여 등 유사 주거지원사업 수혜중인 자
LH, 전북개발공사, 지차체 등이 공급주체인 공공임대주택에 거주중인 자
주택을 소유한 자
부모와 같이 거주하는 자
...
근로기간이 3개월 미만인 자 등 공고문 참고
지원 대상 최대 연령: 49
지원 대상 최소 연령: 18
신청 방법: 제출서류를 지참하여 무주군청 인구활력과 방문 신청
```

### 보낼 이벤트 payload
```json
{
  "rawPolicyId": "0199f3a2-...",
  "version": 1,
  "sourceCode": "youth",
  "provider": "YOUTHCENTER",
  "policyId": "20261012005400213939",
  "field": "BENEFIT",
  "reprocess": false,
  "source": { "title": "청년 취업자 주거비 지원사업", "agency": "전북특별자치도 무주군", "regionScope": "SIGUNGU",
              "regionNames": ["전북특별자치도 무주군"], "regionCodes": ["52730"], "categories": ["주거", "전월세 및 주거급여 지원"],
              "detailUrl": "https://www.youthcenter.go.kr/...", "applyUrl": null },
  "relevant": true,
  "relevanceReason": "무주군 거주 청년의 월세·전세 이자를 지원하는 주거 혜택",
  "summary": "무주군 취업 청년 월세·전세이자 50%, 월 최대 20만 원 12개월",
  "supports": [
    { "kind": "RENT", "amountMax": 20, "amountPer": "MONTH", "months": 12, "ratePct": 50,
      "rawText": "월 임대료 또는 전세 대출 이자 50%를 월 최대 20만원까지 12개월간 지원",
      "evidence": "월 임대료 또는 전세 대출 이자 50%를 월 최대 20만원까지 12개월간 지원" }
  ],
  "schedule": { "applyStart": "2026-01-23", "applyEnd": "2026-02-02", "applyAlways": false,
                "businessStart": "2026-01-01", "businessEnd": "2026-12-31", "rawText": "20260123 ~ 20260202" },
  "howToApply": "제출서류를 지참해 무주군청 인구활력과 방문 신청",
  "documents": [],
  "contact": null,
  "conditions": [
    { "type": "AGE", "value": {"min": 18, "max": 49}, "group": 1, "known": true, "origin": "RULE",
      "rawText": "지원 대상 연령 18~49세", "evidence": "지원 대상 최소 연령: 18", "confidence": 1 },
    { "type": "EMPLOYMENT", "value": {"in": ["EMPLOYED", "SELF_EMPLOYED", "FREELANCER", "DAILY_WORKER", "OTHER"]},
      "group": 2, "known": true, "origin": "RULE",
      "rawText": "재직자, 자영업자, 프리랜서, 일용근로자, 기타", "evidence": "취업 상태: 0013001,0013002,0013004,0013005,0013009", "confidence": 1 },
    { "type": "RESIDENCE", "value": {"regions": ["52730"]}, "group": 3, "known": true, "origin": "RULE",
      "rawText": "무주군 거주", "evidence": "무주군에 거주하며 취업중인 청년에게 주거비 지원", "confidence": 1 },
    { "type": "INCOME_MEDIAN_PCT", "value": {"max": 180, "basis": "HOUSEHOLD"}, "group": 4, "known": true, "origin": "AI",
      "rawText": "가구 기준중위소득 180% 이하", "evidence": "소득 기타 조건: 가구 기준중위소득 180% 이하", "confidence": 0.95 },
    { "type": "HOMELESS", "value": {"basis": "PERSON"}, "group": 5, "known": true, "origin": "AI",
      "rawText": "주택을 소유한 자 제외", "evidence": "주택을 소유한 자", "confidence": 0.85 },
    { "type": "EXCLUSIVE", "value": {}, "group": 6, "known": false, "origin": "AI",
      "rawText": "주거급여 등 유사 주거지원사업 수혜 중이면 제외", "evidence": "주거급여 등 유사 주거지원사업 수혜중인 자", "confidence": 0.9 },
    { "type": "OTHER", "value": null, "group": 7, "known": false, "origin": "AI",
      "rawText": "공공임대주택 거주자 제외", "evidence": "공급주체인 공공임대주택에 거주중인 자", "confidence": 0.9 },
    { "type": "OTHER", "value": null, "group": 8, "known": false, "origin": "AI",
      "rawText": "부모와 같이 거주하면 제외", "evidence": "부모와 같이 거주하는 자", "confidence": 0.9 },
    { "type": "OTHER", "value": null, "group": 9, "known": false, "origin": "AI",
      "rawText": "근로기간 3개월 미만 제외", "evidence": "근로기간이 3개월 미만인 자", "confidence": 0.9 }
  ],
  "quality": { "confidence": 0.7, "needsReview": false, "reviewReasons": ["NO_DOCUMENT"],
               "hasDocument": false, "documentStatus": "NONE",
               "model": "claude-sonnet-5-5", "promptVersion": "policy-v1", "extractedAt": "2026-10-19T07:00:00Z" }
}
```

### 저장 결과
- `benefits` 1줄: 제목·기관·지역(`52730`)은 `source` 그대로, `apply_end = 2026-02-02`라서 `status = CLOSED`
- `benefit_supports` 1줄: `RENT`, 20만 원/월, 12개월, 50%
- `benefit_conditions` 9줄: 판정에 쓰는 줄 5개(`AGE`, `EMPLOYMENT`, `RESIDENCE`, `INCOME_MEDIAN_PCT`, `HOMELESS`) + 글만 보여줄 줄 4개

## 6. 결정이 필요한 것

1. **지역 이름 → 코드**를 누가 바꿀지: extraction(규칙)이 채워 보낼지, benefit이 저장할 때 바꿀지. 시군구 코드표를 어디에 둘지는 condition-types 6장 4번과 같이 정해요. (여러 지역 정책 알림은 정함: `BenefitPublished`가 `regionScope`·`regionCodes`를 모두 담아요, 2026-10-26)
2. **같은 정책 합치기**: 보조금24·복지로·온통청년에 같은 정책이 따로 올라와요. benefit에서 합칠지(대표 한 줄 + 출처 여러 개), 지금처럼 출처마다 한 줄로 둘지
3. **"제외 대상" 조건**: "주택을 소유한 자 제외"를 `HOMELESS`로 바꾸는 것처럼 뒤집을 수 있는 건 뒤집고, 못 뒤집는 건 `OTHER`로 둘지. condition-types에 `negate` 칸을 둘지
4. **창업 조건 type**: `APPLICANT_TYPE`(개인·법인·예비창업자), `COMPANY_TYPE`(중소기업·소상공인·벤처) 추가
5. **온통청년 `연령 제한 여부: N`인데 나이 칸이 18~49**인 경우가 있어요. 이 칸을 "제한 없음"으로 읽을지, 나이 칸을 믿을지 실제 데이터로 확인이 필요해요
6. `needsReview` 정책을 사용자에게 보여줄지 (보여주되 "조건 확인 필요"로 표시할지, 확인 전까지 숨길지)
