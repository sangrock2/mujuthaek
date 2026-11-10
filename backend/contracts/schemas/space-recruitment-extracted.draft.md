# 사업공간 모집 추출 결과 계약 · space_recruitments 테이블 (초안 v0)

창업지원 공고 중 **사업공간 모집**(창업보육센터·공유오피스 입주기업 모집, 업무시설 임대 공급)을
수집(`raw.policy.collected`, `field = SPACE_RECRUITMENT`) → AI 추출(extraction) → benefit 모듈 저장까지 잇는 약속이에요.
지원 정책(`BENEFIT`·`STARTUP_SUPPORT`)은 [policy-extracted.draft.md](policy-extracted.draft.md)의 `benefits`에, 사업공간 모집은 이 문서의 `space_recruitments`에 저장해요 (2026-10-22 결정).

- 보내는 쪽: extraction `rules/space_recruitment` (담당자3), 공통 추출·검증 코드 (담당자2)
- 받는 쪽: api `benefit` 모듈 (담당자3)
- 조건 한 줄의 모양과 type 목록은 [benefit-condition-types.draft.md](benefit-condition-types.draft.md)를 따라요 (창업 조건 type은 그 문서 6장 4번)
- 상태: **이벤트 계약 확정** (2026-10-22, 같은 날 `hqRelocation` 추가. 아직 보내고 받는 코드가 없어 v1을 고쳤어요) → [`contracts/events/space-recruitment.extracted.v1.json`](../events/space-recruitment.extracted.v1.json). 칸·필수 여부·값 범위는 그 파일이 기준이에요. 4장 테이블은 아직 초안이에요 (api 마이그레이션 전)

## 1. 나누는 기준

| 분류 (`field`) | 예 | 저장 테이블 |
| --- | --- | --- |
| `BENEFIT` | 청년 월세 지원, 귀농 정착금 | `benefits` |
| `STARTUP_SUPPORT` | 창업 지원금·정책자금, **창업 임대료 지원**(공간을 빌려주지 않고 임대료를 대신 내줌) | `benefits` |
| `SPACE_RECRUITMENT` | 창업센터 **입주기업 모집**, 업무시설 **임대 공급** (공간을 직접 빌려줌) | `space_recruitments` |
| (수집 안 함) | **상가 모집**: 전통시장 청년몰 입점, 상가 임대공급, 청년상인·점포운영자 모집 (2026-10-22 결정) | — |

- 수집기가 목록 단계에서 이름으로 나눠요 (`sources/policy/base.py` `SPACE_RECRUIT`). 2026-10-22 로컬 데이터 기준 수집 완료 33건 (K-Startup 29, 온통청년 4)
- 상가 모집은 거름에서 SKIPPED로 두고 사업공간으로도 나누지 않아요 (`base.SHOP_RECRUIT`). 점포 임차료 지원·상가 임대료 감면은 지원 정책으로 수집해요
- 원본은 수집 DB `raw_policies` 한 테이블에 두고 `field` 칸으로 나눠요
- 이름으로 잘못 나눈 공고는 AI가 `relevant=false`로 돌려줘요 (예: '입주기업 대상 마케팅 지원 모집'). benefit은 숨겨요

## 2. 흐름

```
collector ──raw.policy.collected (field=SPACE_RECRUITMENT)──▶ extraction ──space-recruitment.extracted──▶ api benefit
                                                               rules/space_recruitment              space_recruitments 저장
```

extraction은 `field`로 추출 규칙을 골라요 (`RULES_BY_FIELD`). 이벤트를 따로 두는 이유는 결과 모양(공간·호실·임대료)이 지원 정책과 달라서예요.

## 3. 이벤트 `space-recruitment.extracted` v1 (확정)

모든 칸이 필수예요. 값이 없으면 칸을 빼지 않고 `null`(목록은 빈 목록)로 보내요. `known=false`인 조건은 `value`가 `null`이어야 해요.

봉투(`eventId`, `eventType`, `schemaVersion`, `occurredAt`, `producer: "extraction"`)는 다른 이벤트와 같아요. 입력 한 건마다 한 건을 보내요.

| 칸 | 모양 | 뜻 | 누가 채움 |
| --- | --- | --- | --- |
| `rawPolicyId`, `version`, `sourceCode`, `provider`, `policyId`, `reprocess` | | `policy.extracted`와 같아요 | 받은 그대로 |
| `source` | object | 통일 기본 칸 (`policy.extracted` 3-1과 같아요) | 받은 그대로 |
| `relevant` | bool | 정말 공간을 빌려주는 모집 공고인지. false면 benefit은 숨겨요 | AI |
| `relevanceReason` | string | 판단 이유 한 문장 | AI |
| `summary` | string \| null | 화면에 보일 한 줄 요약 (80자 안) | AI |
| `facility` | object | 시설 (3-1) | AI |
| `units` | array | 모집하는 공간 (3-2). 종류·크기·임대료가 다르면 줄을 나눠요 | AI |
| `recruitCount` | int \| null | 모집 기업·팀 수 | AI |
| `residency` | object | 입주 기간 (3-3) | AI |
| `hqRelocation` | object | 입주 후 본점 이전 의무 (3-4, 2026-10-22 추가) | AI |
| `schedule` | object | 신청 기간 (`policy.extracted` 3-3과 같아요) | 규칙 → 없으면 AI |
| `selectionMethod` | string \| null | 선정 방법 요약 (서류·발표 평가 등) | AI |
| `support` | string[] | 입주하면 함께 받는 지원 (멘토링, 투자 연계 …) | AI |
| `howToApply`, `documents`, `contact` | | `policy.extracted`와 같아요 | AI |
| `conditions` | array | 입주 자격 ([condition-types](benefit-condition-types.draft.md) 모양 + `origin`). 업력·업종·지역·대표자 나이 등 | 규칙 + AI |
| `quality` | object | `policy.extracted` 3-4와 같아요 | extraction |

### 3-1. `facility`

| 칸 | 모양 | 뜻 |
| --- | --- | --- |
| `name` | string \| null | 시설 이름 ('서울창업센터 동작') |
| `kind` | enum | `INCUBATOR` 창업보육센터·창업센터, `SHARED_OFFICE` 공유오피스, `OFFICE` 사무실·업무시설, `FACTORY` 공장·제조공간, `OTHER` |
| `address` | string \| null | 주소 원문 |
| `evidence` | string | 원문 문장 |

### 3-2. `units[]`

| 칸 | 모양 | 뜻 |
| --- | --- | --- |
| `name` | string \| null | 공간 이름 ('1인실', '4인실', 'A동 201호') |
| `count` | int \| null | 호실·좌석 수 |
| `areaM2` | number \| null | 전용 면적 (㎡). 평이면 ㎡로 바꿔요 |
| `seats` | int \| null | 좌석·인원 수 |
| `deposit` | int \| null | 보증금 (원) |
| `monthlyRent` | int \| null | 월 임대료 (원). 무상이면 0 |
| `maintenanceFee` | int \| null | 월 관리비 (원) |
| `rawText`, `evidence` | string | 원문, 원문이 들어 있는 문장 |

금액은 **원** 단위예요 (`benefit_supports`는 만 원). 관리비·소액 임대료가 만 원 아래로 자주 나와서예요.

### 3-3. `residency`

| 칸 | 모양 | 뜻 |
| --- | --- | --- |
| `months` | int \| null | 기본 입주 기간 (개월) |
| `extendableMonths` | int \| null | 연장할 수 있는 최대 기간 (개월) |
| `moveInDate` | date \| null | 입주 예정일 |
| `rawText` | string \| null | 원문 |

### 3-4. `hqRelocation` (2026-10-22 추가)

'입주 확정 시 3개월 이내 본점 소재지 이전'처럼 **입주 후 지킬 의무**예요. 입주 자격(`conditions`의 `BUSINESS_LOCATION`)으로 넣으면
아직 다른 지역에 있는 기업이 '지원 불가'로 나와서 따로 둬요. 판정하지 않고 화면에 보여만 줘요. 2026-10-22 기준 사업공간 모집 29건 중 10건에 있어요.

| 칸 | 모양 | 뜻 |
| --- | --- | --- |
| `mandatory` | bool \| null | true 이전 필수, false 이전하지 않아도 됨이 글에 있음, null 글에 없음 |
| `withinMonths` | int \| null | 이전 기한 (입주·계약 후 개월). 기한이 없으면 null |
| `rawText`, `evidence` | string \| null | 원문, 원문이 들어 있는 문장 |

## 4. 테이블 (api DB, 스키마 `benefit`)

3장의 추출 칸 + 지역(`source.regionScope`·`regionNames`·`regionCodes`)으로 저장해요 (2026-10-22 결정). 테이블 설명은 [space-recruitments.draft.md](space-recruitments.draft.md)에 있어요.

## 5. 결정이 필요한 것

1. ~~이벤트 이름~~: `space-recruitment.extracted`로 따로 둬요 (2026-10-22 확정)
2. **판정**: 입주 자격(업력·업종·지역)을 eligibility가 판정할지. type은 condition-types 3-5의 `STARTUP_STAGE`·`BUSINESS_YEARS`·`INDUSTRY`·`BUSINESS_LOCATION`을 써요 (본점 이전 의무는 판정 대상이 아니에요, 3-4)
3. **관심 공고·알림**: 회원의 관심 공고(요구사항 3-12)에 사업공간 모집도 넣을지. 넣으면 관심 공고 테이블이 `benefits`·`space_recruitments` 둘을 가리킬 수 있어야 해요
4. **공고(notice) 모듈의 사업공간 공고(PR #33 `BUSINESS_SPACE`)와의 관계**: LH 상가·업무시설 공고는 notice, 창업지원 API의 입주 모집은 여기예요. 화면에서 함께 보여줄지 담당자2와 정해요
