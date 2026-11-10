# 혜택 자격 조건 type 약속표 (초안 v0)

benefit 모듈이 저장하는 자격 조건(`benefit_conditions`)과 eligibility 규칙 엔진이 읽는 조건의 약속이에요.
AI 추출 양식, benefit 저장, eligibility 판정이 모두 이 표를 따라요.

- 쓰는 쪽: extraction(AI 추출) → benefit 모듈 (담당자3)
- 읽는 쪽: eligibility 모듈 `eligibility/rule` (판정·준비할 돈)
- 상태: **초안**이에요. eligibility 담당자 확인 후 v1로 확정하고 JSON Schema(`benefit-condition.v1.json`)로 옮겨요.

## 1. 조건 한 줄의 모양

```json
{
  "type": "INCOME_MEDIAN_PCT",
  "value": { "max": 180, "basis": "HOUSEHOLD" },
  "group": 1,
  "known": true,
  "rawText": "가구 기준중위소득 180% 이하",
  "evidence": "신청자격: 무주군에 거주하는 … 가구 기준중위소득 180% 이하인 청년",
  "confidence": 0.9
}
```

| 칸 | 뜻 |
| --- | --- |
| `type` | 아래 표의 조건 종류. 표에 없는 값은 쓰지 않아요 (없으면 `OTHER`) |
| `value` | type마다 정해진 모양. 비교 방법(이상·이하·포함)은 type이 정해요 |
| `group` | 같은 번호끼리는 "또는", 다른 번호끼리는 "그리고" |
| `known` | 글에 조건은 있는데 값으로 못 바꿨으면 `false`. `value`는 비워요 |
| `rawText` | 조건 원문 (화면의 판정 근거) |
| `evidence` | 원문이 들어 있는 문장. 원문에 그대로 있어야 해요 (검증) |
| `confidence` | AI 신뢰도 0~1. 규칙으로 옮긴 값은 1 |

**조건 줄이 없으면 "제한 없음"**이에요. "결혼 상태: 제한 없음" 같은 줄은 만들지 않아요.

### 그룹 예시
"만 19~39세이면서, 신혼부부 또는 한부모가족"

| group | type | value |
| --- | --- | --- |
| 1 | `AGE` | `{"min":19,"max":39}` |
| 2 | `MARITAL` | `{"in":["NEWLYWED"]}` |
| 2 | `HOUSEHOLD_TYPE` | `{"in":["SINGLE_PARENT"]}` |

## 2. 판정 결과 (eligibility)

조건 한 줄마다 세 가지 중 하나예요.

| 결과 | 언제 |
| --- | --- |
| `PASS` | 사용자 값이 조건을 만족 |
| `FAIL` | 사용자 값이 조건을 벗어남 |
| `UNKNOWN` | `known=false`이거나, 사용자가 그 항목을 입력하지 않았거나, 입력 항목이 아직 없는 조건 |

정책 전체는 FAIL이 하나라도 있으면 **지원 불가**, 모두 PASS면 **지원 가능**, 나머지는 **조건 확인 필요**예요.
그룹 안에서는 하나라도 PASS면 PASS, 모두 FAIL이면 FAIL, 그 밖은 UNKNOWN이에요.

## 3. 조건 type 목록

"사용자 입력" 칸은 서비스 요약의 입력 정보 기준이에요. **⚠️는 지금 입력 항목에 없는 조건**이라 결정이 필요해요 (6장).

### 3-1. 사람

| type | 뜻 | value | 사용자 입력 |
| --- | --- | --- | --- |
| `AGE` | 만 나이 | `{"min":19,"max":39}` 둘 다 포함, 한쪽만 있어도 됨 | 나이 |
| `MARITAL` | 혼인 상태 | `{"in":["SINGLE","MARRIED","NEWLYWED","ENGAGED"]}` | 결혼 여부 |
| `NEWLYWED_YEARS` | 혼인 기간 | `{"max":7}` (년) | ⚠️ 혼인 신고일 |
| `CHILDREN` | 자녀 | `{"minCount":2,"maxAgeOfYoungest":7}` | 자녀 (수, 나이) |
| `PREGNANCY` | 임신·출산 | `{"in":["PRE_PARENT","PREGNANT","BIRTH"],"months":12}` (`months`: 출산 후 몇 개월 안) | ⚠️ |
| `HOUSEHOLD_TYPE` | 가구 유형 | `{"in":["SINGLE_PERSON","SINGLE_PARENT","GRANDPARENT","MULTI_CHILD","MULTICULTURAL","NK_DEFECTOR","EXTENDED"]}` | ⚠️ (일부는 자녀 입력으로 계산) |
| `WELFARE_STATUS` | 복지 수급 | `{"in":["BASIC_LIVELIHOOD","NEAR_POOR"]}` (기초생활수급, 차상위) | ⚠️ |
| `SPECIAL_STATUS` | 특수 대상 | `{"in":["DISABLED","VETERAN","ILLNESS","PROTECTED_YOUTH","SOLDIER"]}` | ⚠️ |

### 3-2. 소득·자산

| type | 뜻 | value | 사용자 입력 |
| --- | --- | --- | --- |
| `INCOME_MEDIAN_PCT` | 기준중위소득 비율 | `{"max":180,"basis":"HOUSEHOLD"}` basis: `HOUSEHOLD`, `PERSONAL` | 연봉 + 가구원 수 + 그 해 기준중위소득(직접 관리) |
| `INCOME_AMOUNT` | 소득 금액 | `{"max":5000,"unit":"MANWON_PER_YEAR","basis":"PERSONAL"}` | 연봉 |
| `ASSET_AMOUNT` | 자산 금액 | `{"max":34500,"unit":"MANWON","kind":"TOTAL"}` kind: `TOTAL`, `CAR`, `REAL_ESTATE`, `FINANCIAL` | 자산 |

소득·자산은 사용자 값을 저장하지 않고 판정에만 써요 (CLAUDE.md 규칙).

### 3-3. 거주·집

| type | 뜻 | value | 사용자 입력 |
| --- | --- | --- | --- |
| `RESIDENCE` | 지금 사는 곳 | `{"regions":["52730"]}` 시도 2자리 또는 시군구 5자리 코드 | 현재 거주 지역 |
| `RESIDENCE_MONTHS` | 그 지역 거주 기간 | `{"min":6,"regions":["52730"]}` (개월) | ⚠️ 전입일 |
| `MOVE_IN` | 전입(예정)자 | `{"regions":["52730"],"withinMonths":12}` 전입 후 N개월 안 신청 | 판정하지 않고 **"전입하면 받을 수 있음"**으로 표시 |
| `HOMELESS` | 무주택 | `{"basis":"HOUSEHOLD"}` basis: `PERSON`, `HOUSEHOLD` | 무주택 기간(0보다 크면 무주택) |
| `HOMELESS_YEARS` | 무주택 기간 | `{"min":1}` (년) | 무주택 기간 |
| `LEASE` | 지금 임차 조건 | `{"kind":["MONTHLY","JEONSE"],"depositMax":5000,"monthlyMax":60,"unit":"MANWON"}` | ⚠️ 지금 보증금·월세 |
| `FIRST_HOME` | 생애 최초 구입 | `{}` | 무주택 기간으로 일부 판단 |

`MOVE_IN`은 이주 혜택의 핵심이에요. 지금 다른 곳에 살아도 대상이라 FAIL로 처리하면 안 돼요.

### 3-4. 일·학업

| type | 뜻 | value | 사용자 입력 |
| --- | --- | --- | --- |
| `EMPLOYMENT` | 취업 상태 | `{"in":["EMPLOYED","SELF_EMPLOYED","UNEMPLOYED","FREELANCER","DAILY_WORKER","SHORT_TERM","STARTUP","OTHER"]}` | ⚠️ |
| `EDUCATION` | 학력·재학 | `{"in":["ELEMENTARY","MIDDLE","BELOW_HIGH","HIGH_ENROLLED","HIGH_GRAD_EXPECTED","HIGH_GRAD","UNIV_ENROLLED","UNIV_GRAD_EXPECTED","UNIV_GRAD","GRADUATE","OTHER"]}` | ⚠️ |
| `OCCUPATION` | 직업 분야 | `{"in":["FARMER","FISHER","LIVESTOCK","FORESTRY"]}` | ⚠️ |
| `WORKPLACE` | 직장 조건 | `{"kind":["SME"],"regions":["52730"]}` (중소기업, 관내 사업장) | 직장 위치 (규모는 ⚠️) |

### 3-5. 사업 (사업공간 카테고리)

| type | 뜻 | value | 사용자 입력 |
| --- | --- | --- | --- |
| `STARTUP_STAGE` | 창업 상태 | `{"in":["PRE_STARTUP","OPERATING","CLOSING"]}` | 창업 상태 |
| `BUSINESS_YEARS` | 업력 | `{"max":7}` (년) | 업력 |
| `INDUSTRY` | 업종 | `{"in":["C","I","J"]}` 한국표준산업분류 대분류 (C 제조, I 숙박·음식, J 정보통신 …) | 업종 |
| `REVENUE` | 매출 | `{"max":30000,"unit":"MANWON_PER_YEAR"}` | 매출 |
| `EMPLOYEES` | 직원 수 | `{"max":4}` | 직원 수 |
| `BUSINESS_LOCATION` | 사업장 소재지 | `{"regions":["11"]}` | 희망 지역 |

### 3-6. 판정하지 않는 조건 (글만 보여줌)

| type | 뜻 | value |
| --- | --- | --- |
| `EXCLUSIVE` | 중복 수혜 불가 | `{}` + rawText (예: "청년월세 특별지원과 중복 불가") |
| `PRIORITY` | 선정 우선순위·가점 | `{}` + rawText (자격이 아니라 뽑는 순서라 판정에 쓰지 않음) |
| `OTHER` | 위 표로 못 담는 조건 | `{}` + rawText, `known=false` → 항상 UNKNOWN |

## 4. 코드 사전 (value 안의 값)

공식 코드표(온통청년 `API코드정보.xlsx`, 보조금24 Swagger)는 **이름만** 주고 정의는 주지 않아요. 아래 "뜻"은 일반적인 정책 용어 기준이고, 정책마다 세부 기준이 다르면 `rawText`가 우선해요.

### 공통 단위·기준

| 값 | 뜻 |
| --- | --- |
| 지역 코드 | 시도 2자리(`52` 전북) 또는 시군구 5자리(`52730` 무주군). 시도 코드는 그 시도 전체 |
| `MANWON` | 만 원 (5000 = 5천만 원) |
| `MANWON_PER_YEAR` | 연 만 원 |
| `HOUSEHOLD` | 세대(가구) 전체 기준. 주민등록상 같은 세대원 모두 |
| `PERSON`, `PERSONAL` | 본인 기준 |

### MARITAL (혼인 상태)

| 값 | 뜻 |
| --- | --- |
| `SINGLE` | 미혼. 혼인 신고를 하지 않은 사람 |
| `MARRIED` | 기혼. 혼인 신고를 한 사람 (기간 무관) |
| `NEWLYWED` | 신혼부부. 혼인 신고 후 일정 기간 안. 기간은 `NEWLYWED_YEARS` (흔히 7년) |
| `ENGAGED` | 예비 신혼부부. 결혼 예정으로 정해진 기간 안에 혼인 신고할 사람 |

### PREGNANCY (임신·출산)

| 값 | 뜻 | 출처 |
| --- | --- | --- |
| `PRE_PARENT` | 예비부모·난임 부부 | 보조금24 JA0301 |
| `PREGNANT` | 임신 중 | JA0302 |
| `BIRTH` | 출산 또는 입양한 사람. `months`가 있으면 그 개월 안 | JA0303 |

### HOUSEHOLD_TYPE (가구 유형)

| 값 | 뜻 | 출처 |
| --- | --- | --- |
| `SINGLE_PERSON` | 1인 가구 | JA0404 |
| `SINGLE_PARENT` | 한부모가족 (부 또는 모 혼자 자녀 양육) | JA0403, 온통청년 0014004 |
| `GRANDPARENT` | 조손가족 (조부모가 손자녀 양육) | JA0403 |
| `MULTI_CHILD` | 다자녀 가구. 자녀 수 기준은 정책마다 달라서 `CHILDREN.minCount`를 같이 둬요 | JA0411 |
| `MULTICULTURAL` | 다문화가족 (결혼이민자·귀화자가 있는 가족) | JA0401 |
| `NK_DEFECTOR` | 북한이탈주민 | JA0402 |
| `EXTENDED` | 확대가족 (3대 이상 함께 사는 가족) | JA0414 |

### WELFARE_STATUS (복지 수급)

| 값 | 뜻 |
| --- | --- |
| `BASIC_LIVELIHOOD` | 국민기초생활보장 수급자 (생계·의료·주거·교육급여 중 하나 이상) |
| `NEAR_POOR` | 차상위계층 (수급자는 아니지만 소득인정액이 기준중위소득 50% 이하) |

### SPECIAL_STATUS (특수 대상)

| 값 | 뜻 | 출처 |
| --- | --- | --- |
| `DISABLED` | 등록 장애인 | JA0328, 0014005 |
| `VETERAN` | 국가보훈대상자 | JA0329 |
| `ILLNESS` | 질병·질환자 | JA0330 |
| `PROTECTED_YOUTH` | 자립준비청년 (보호종료아동) | 글에서 AI |
| `SOLDIER` | 군인 (현역 장병 등) | 0014007 |

### 소득·자산 kind

| 값 | 뜻 |
| --- | --- |
| `TOTAL` | 총자산 (정책이 "총자산"이라고 한 값. 부채 차감 여부는 정책마다 달라 `rawText` 확인) |
| `CAR` | 자동차 가액 |
| `REAL_ESTATE` | 부동산 (토지·건물) |
| `FINANCIAL` | 금융자산 (예금·적금·주식 등) |

### LEASE (지금 임차 조건)

| 값 | 뜻 |
| --- | --- |
| `MONTHLY` | 월세 (보증금 있는 월세 포함) |
| `JEONSE` | 전세 |
| `depositMax` | 임차 보증금 상한 |
| `monthlyMax` | 월세 상한 |

`HOMELESS`는 본인(`PERSON`) 또는 세대원 모두(`HOUSEHOLD`)가 주택을 갖고 있지 않은 상태예요. `FIRST_HOME`은 세대원 모두 과거에도 주택을 가진 적이 없는 상태예요.

### EMPLOYMENT (취업 상태)

| 값 | 뜻 | 출처 |
| --- | --- | --- |
| `EMPLOYED` | 재직자 (회사에 고용된 근로자) | 온통청년 0013001, JA0326 |
| `SELF_EMPLOYED` | 자영업자 (사업자 등록 후 운영) | 0013002 |
| `UNEMPLOYED` | 미취업자·구직자 | 0013003, JA0327 |
| `FREELANCER` | 프리랜서 | 0013004 |
| `DAILY_WORKER` | 일용근로자 | 0013005 |
| `SHORT_TERM` | 단기근로자 | 0013007 |
| `STARTUP` | 창업자·예비창업자 | 0013006 |
| `OTHER` | 기타 | 0013009 |

영농종사자(0013008)는 `OCCUPATION`의 `FARMER`로 옮겨요.

### EDUCATION (학력·재학)

| 값 | 뜻 | 출처 |
| --- | --- | --- |
| `ELEMENTARY` | 초등학생 | JA0317 |
| `MIDDLE` | 중학생 | JA0318 |
| `BELOW_HIGH` | 고졸 미만 | 0049001 |
| `HIGH_ENROLLED` | 고등학교 재학 | 0049002, JA0319 |
| `HIGH_GRAD_EXPECTED` | 고등학교 졸업 예정 | 0049003 |
| `HIGH_GRAD` | 고등학교 졸업 | 0049004 |
| `UNIV_ENROLLED` | 대학 재학 | 0049005, JA0320 |
| `UNIV_GRAD_EXPECTED` | 대학 졸업 예정 | 0049006 |
| `UNIV_GRAD` | 대학 졸업 | 0049007 |
| `GRADUATE` | 석·박사 (재학·졸업) | 0049008, JA0320 |
| `OTHER` | 기타 | 0049009 |

### OCCUPATION (직업 분야)

| 값 | 뜻 | 출처 |
| --- | --- | --- |
| `FARMER` | 농업인 | JA0313, 0013008, 0014006 |
| `FISHER` | 어업인 | JA0314 |
| `LIVESTOCK` | 축산업인 | JA0315 |
| `FORESTRY` | 임업인 | JA0316 |

### WORKPLACE (직장 조건)

| 값 | 뜻 |
| --- | --- |
| `SME` | 중소기업 재직 (0014001) |
| `regions` | 사업장(직장) 소재지 |

### STARTUP_STAGE (창업 상태)

| 값 | 뜻 | 출처 |
| --- | --- | --- |
| `PRE_STARTUP` | 예비창업자 (사업자 등록 전) | JA1101 |
| `OPERATING` | 영업 중 | JA1102 |
| `CLOSING` | 생계 곤란·폐업 예정 | JA1103 |

### INDUSTRY (업종, 한국표준산업분류 대분류)

| 값 | 뜻 | 출처 |
| --- | --- | --- |
| `A` | 농업, 임업 및 어업 | JA2202 |
| `C` | 제조업 | JA1202, JA2201 |
| `G` | 도매 및 소매업 | |
| `I` | 숙박 및 음식점업 | JA1201 |
| `J` | 정보통신업 | JA2203 |
| `M` | 전문, 과학 및 기술 서비스업 | |
| `OTHER` | 기타 업종 | JA1299, JA2299 |

그 밖의 대분류(B, D~F, H, K, L, N~U)도 같은 방식으로 써요.

## 5. 출처 구조화 값 → 조건 (AI 없이 규칙으로)

API가 코드로 주는 값은 추출 단계에서 규칙으로 바로 옮겨요. AI 결과와 다르면 규칙 값을 우선해요.

### 온통청년 (`API코드정보.xlsx`)

| 출처 칸 | → type | 옮기는 법 |
| --- | --- | --- |
| `sprtTrgtMinAge`, `sprtTrgtMaxAge` | `AGE` | 0~0이면 조건 없음 |
| `mrgSttsCd` | `MARITAL` | 0055001 기혼 → `MARRIED`, 0055002 미혼 → `SINGLE`, 0055003 제한없음 → 줄 없음 |
| `earnCndSeCd` + `earnMinAmt`·`earnMaxAmt` | `INCOME_AMOUNT` | 0043002 연소득일 때만. 단위 만 원 (5000 = 5천만 원). 0043003 기타는 `earnEtcCn` 글을 AI가 읽음 |
| `jobCd` | `EMPLOYMENT` | 0013001 재직자 `EMPLOYED`, 002 자영업자 `SELF_EMPLOYED`, 003 미취업자 `UNEMPLOYED`, 004 프리랜서 `FREELANCER`, 005 일용근로자 `DAILY_WORKER`, 006 (예비)창업자 `STARTUP`, 007 단기근로자 `SHORT_TERM`, 008 영농종사자 → `OCCUPATION` `FARMER`, 009 기타 `OTHER`, 010 제한없음 → 줄 없음 |
| `schoolCd` | `EDUCATION` | 0049001 고졸 미만 `BELOW_HIGH`, 002 고교 재학 `HIGH_ENROLLED`, 003 고졸 예정 `HIGH_GRAD_EXPECTED`, 004 고교 졸업 `HIGH_GRAD`, 005 대학 재학 `UNIV_ENROLLED`, 006 대졸 예정 `UNIV_GRAD_EXPECTED`, 007 대학 졸업 `UNIV_GRAD`, 008 석·박사 `GRADUATE`, 009 기타 `OTHER`, 010 제한없음 → 줄 없음 |
| `sbizCd` | 여러 type | 0014001 중소기업 → `WORKPLACE`, 002 여성 → `OTHER`, 003 기초생활수급자 → `WELFARE_STATUS`, 004 한부모가정 → `HOUSEHOLD_TYPE`, 005 장애인 → `SPECIAL_STATUS`, 006 농업인 → `OCCUPATION`, 007 군인 → `SPECIAL_STATUS`, 008 지역인재·009 기타 → `OTHER`, 010 제한없음 → 줄 없음 |
| `zipCd` | `RESIDENCE` | 시군구 코드. 여러 개면 모두 |

쉼표로 여러 코드가 오면 같은 group의 한 줄(`in` 목록)로 넣어요.

### 보조금24 지원조건 (`JA0101`~`JA2299`)

묶음 단위로 읽어요. **묶음이 모두 Y이거나 모두 null이면 줄을 만들지 않아요.** 일부만 Y인 묶음만 조건이 돼요.

| 묶음 | 코드 | → type |
| --- | --- | --- |
| 성별 | JA0101~0102 | `OTHER` (성별 입력 없음) |
| 나이 | JA0110~0111 | `AGE` (120 이상은 상한 없음) |
| 소득 | JA0201~0205 | `INCOME_MEDIAN_PCT` (Y인 구간의 최댓값. 예: 0~50%, 51~75%만 Y → `max 75`) |
| 출산 | JA0301~0303 | `PREGNANCY` |
| 직업·학생 | JA0313~0316 | `OCCUPATION` |
| | JA0317~0320 | `EDUCATION` |
| | JA0326~0327 | `EMPLOYMENT` |
| | JA0328~0330 | `SPECIAL_STATUS` |
| 가구 | JA0401~0404, 0411, 0414 | `HOUSEHOLD_TYPE` |
| | JA0412 무주택세대 | `HOMELESS` |
| | JA0413 신규전입 | `MOVE_IN` |
| 소상공인 | JA1101~1103 | `STARTUP_STAGE` |
| | JA1201~1299 | `INDUSTRY` |

"모두 Y = 제한 없음"은 공식 명세가 아니라 실제 데이터를 보고 한 해석이에요. 지원조건 값은 정부24 맞춤 찾기용 체크 표시라, 지원대상·선정기준 글과 다르면 AI가 읽은 글을 우선해요.

### 복지로 (`trgterIndvdlArray` 가구유형, `lifeArray` 생애주기)

태그가 실제 내용과 안 맞는 경우가 많아서(관심주제 '주거' 55건 중 주거 정책 4건) **조건으로 옮기지 않고 AI 참고값으로만** 넘겨요. 조건은 `tgtrDtlCn`, `slctCritCn` 글에서 AI가 뽑아요.

## 6. 결정이 필요한 것

1. **⚠️ 입력 항목에 없는 조건**을 어떻게 할지: 입력 항목을 늘릴지, 늘 UNKNOWN("조건 확인 필요")으로 둘지
   - 자주 나올 것으로 보이는 것: `EMPLOYMENT`(청년 정책에 많음), `RESIDENCE_MONTHS`(지자체 정책), `LEASE`(월세 지원), `WELFARE_STATUS`
2. `INCOME_MEDIAN_PCT` 계산에 필요한 **가구원 수**: 입력의 "부양가족 수"로 대신할지
3. `MARITAL`의 `NEWLYWED`(신혼) 기준: 혼인 7년 이내가 많지만 정책마다 달라서 `NEWLYWED_YEARS`를 따로 둘지
4. 지역 코드 기준: 시군구 코드표를 어느 것으로 할지 (온통청년 `zipCd`는 법정동 시군구 5자리, 통합특별시 같은 새 이름 반영 필요)
5. `INDUSTRY` 코드: 한국표준산업분류 대분류로 충분한지
