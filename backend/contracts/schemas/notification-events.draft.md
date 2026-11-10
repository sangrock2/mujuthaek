# 알림 서버 이벤트 계약 (초안 v1)

알림 서버(`services/notification`)가 받는 이벤트는 **3개**예요. 모두 api가 보내요.

| 이벤트 | 보내는 곳 | 뜻 |
| --- | --- | --- |
| `notification.requested` | api `notification` 모듈 | "이 회원들에게, 이 주소로, 이 문구를 보내 주세요" |
| `email.verification.requested` | api `user` 모듈 | "이 주소로 이메일 인증 코드를 보내 주세요" |
| `user.withdrawn` | api `user` 모듈 | "이 회원이 탈퇴했어요. 발송 기록을 지워 주세요" |

나중에 알림 서버가 보내는 이벤트: `email.bounced` (SES 반송·스팸 신고 → api가 이메일 상태를 바꿈, 6장), `push.subscription.expired` (죽은 푸시 구독 → api가 그 기기를 지움, [web-push.draft.md](web-push.draft.md) 5장).

**역할 나누기 (2026-10-23 결정, B안)**
- **PWA는 api만 불러요.** 이메일 등록·인증, 알림 설정, 알림함은 모두 api에 있어요. 알림 서버에는 화면이 부르는 API도, 로그인 확인도 없어요
- **api가 "누구에게, 어디로, 무엇을"** 정해요
  - 대상자 찾기, 마감 D-3·D-1 계산 (`notification` 모듈)
  - 회원 설정 확인: 이메일 켬, 종류별 켬, 인증된 주소 (`user` 모듈 조회 메서드)
  - 알림 문구 만들기, 알림함 기록 (`notification` 모듈)
- **알림 서버는 "언제, 어떻게"**만 해요
  - 조용한 시간, 묶음 메일, 중복 방지
  - SES 발송, 재시도, 반송 받기
  - 받은 값을 다시 따지지 않아요
- 상태: **초안**이에요. 확인 뒤 `contracts/events/*.v1.json`으로 옮겨요

```
PWA ──HTTP──▶ api
               ├ user          이메일 등록·인증, 알림 설정 (account 스키마)
               ├ notice·benefit 내부 이벤트 NoticePublished·NoticeUpdated·BenefitPublished …
               └ notification  대상자 찾기 → 설정 확인·주소 붙이기 → 문구 → 알림함 기록
                               → 500명씩 notification.requested → api 아웃박스 (같은 트랜잭션)
                                                                 │ 릴레이
                                                                 ▼
                                   mujuthaek.events ──▶ mujuthaek.notification ──▶ 알림 서버
                                                           발송 줄 → 조용한 시간·묶음 → SES → 결과
```

## 1. 공통

### 봉투

다른 이벤트(`extraction.completed` 등)와 같아요.

| 칸 | 값 |
| --- | --- |
| `eventId` | UUID v7. 알림 서버는 `processed_events`로 한 번만 처리해요 |
| `eventType` | 위 3개 중 하나 (= RabbitMQ 라우팅 키) |
| `schemaVersion` | `1` |
| `occurredAt` | 사건이 일어난 시각 (ISO 8601) |
| `producer` | `api` |
| `traceId` | 비어 있어도 돼요 |
| `payload` | 아래 |

### 보내는 방법: api 아웃박스 (아직 없음, 먼저 필요)

담당자3이 만들고 담당자1이 리뷰해요 (2026-10-23 결정).
- 테이블 `common.outbox`: Python 쪽(`services/extraction/migrations/V202610151700__extraction_jobs_review_outbox.sql`의 `outbox`)과 같은 칸 — `event_id`, `event_type`, `schema_version`, `payload`(봉투 전체), `created_at`, `published_at`, `attempts`
- 적기: 공고 저장 등과 **같은 트랜잭션**에서 한 줄 (커밋 뒤에 적거나 RabbitMQ로 바로 보내면 그 사이 api가 죽을 때 사라져요)
- 릴레이: 1초마다 안 보낸 줄을 `mujuthaek.events`로 보내고, RabbitMQ가 받았다고 하면 `published_at` 기록
- 이메일 주소·인증 코드가 실려요. 보낸 줄(`published_at` 있음)은 하루 뒤 지워요

### 개인 정보

- 메시지에 이메일 주소(`recipients[].email`, `email`)와 인증 코드가 실려요. RabbitMQ와 실패 큐(`mujuthaek.notification.dlq`) 밖으로 내보내지 않아요
- 알림 서버는 주소를 보내는 동안만 `deliveries.address`에 두고, 끝나면(SENT·FAILED) 지워요. 인증 코드는 저장하지 않아요
- 로그에는 `userId`·`eventId`만 남겨요

## 2. `notification.requested`

알림 한 건을 회원 여러 명(최대 500명)에게 보내 달라는 요청이에요. 대상이 500명을 넘으면 api가 여러 이벤트로 나눠 보내요 (이벤트마다 `eventId`는 다르고 `dedupKey`는 같아요).

### payload

| 칸 | 모양 | 필수 | 뜻 |
| --- | --- | --- | --- |
| `type` | enum | ✅ | `NEW_NOTICE` 새 주거·사업공간 공고 · `NEW_SUPPORT` 새 지원 정책·창업지원 · `DEADLINE_D3`·`DEADLINE_D1` 관심 공고 마감 · `CORRECTED` 관심 공고 정정 · `FOLLOW_UP` 관심 공고 후속 안내 · `REPORT_ANSWERED` 회원 제보에 관리자가 답함. 알림 서버는 묶음 여부(NEW_*만 묶음)에만 써요 |
| `dedupKey` | string | ✅ | 같은 알림인지 가리는 열쇠 (회원 ID 빼고). 아래 표. 알림 서버는 `{userId}:{dedupKey}`·채널마다 한 번만 보내요 |
| `target.type` | `NOTICE` \| `BENEFIT` \| `STARTUP_SUPPORT` \| `SPACE_RECRUITMENT` | ✅ | ID가 들어 있는 api 테이블 (`notices` / `benefits` / 창업지원 사업·사업공간 모집은 `notice.policy_judgments`, ID = rawPolicyId). 추적용이에요 |
| `target.id` | uuid | ✅ | 그 테이블의 ID |
| `title` | string | ✅ | api가 만든 알림 제목. 메일 제목·알림함과 같아요 (3장 문구 예) |
| `body` | string | ✅ | api가 만든 알림 본문 |
| `linkPath` | string | ✅ | PWA 화면 경로 (주거 공고 `/notices/{id}`, 사업공간 공고 `/business/spaces/{id}`, 혜택 `/benefits/{id}`, 창업지원 사업 `/business/support/{id}`, 사업공간 모집 `/business/spaces/{id}`. 정책 둘은 맞춤 목록과 같은 정책 ID) |
| `recipients` | object[] | ✅ 1~500개 | 받을 회원 |
| `recipients[].userId` | uuid | ✅ | |
| `recipients[].email` | string \| null | ✅ | 이메일로 보낼 주소. api가 **이메일 켬 + 이 종류 켬 + 인증됐고 ACTIVE**일 때만 넣어요. null이면 이메일로 안 보내요 |
| `recipients[].quietEnabled` | boolean | ✅ | 22:00~08:00 알림을 08:00에 보내기 |
| `recipients[].inboxId` | uuid | | 이 회원의 알림함 줄 ID. 알림 서버가 웹 푸시에 `ids`로 실어 보내면 기기가 「떴어요·눌렀어요」를 api에 알려요 |

웹 푸시: `recipients[].push`(구독 기기 목록, 없으면 null)를 더해요. api가 "이 종류 켬 + 기기 있음"일 때만 넣어요 (따로 `push_enabled`는 없어요). 모양·보내는 방법은 [web-push.draft.md](web-push.draft.md)

### dedupKey 규칙 (api가 만들어요)

| type | dedupKey | 결과 |
| --- | --- | --- |
| NEW_NOTICE·NEW_SUPPORT | `{target.type}:{target.id}:NEW` | 관심 조건과 관심 공고에 둘 다 걸려도 1번 |
| DEADLINE_D3·D1 | `{target.type}:{target.id}:D3:{applyEnd}` | 정정으로 마감일이 바뀌면 새 날짜 기준으로 다시 1번 |
| CORRECTED | `{target.type}:{target.id}:CORRECTED:{version}` | 정정 회차마다 1번 |
| FOLLOW_UP | `{target.type}:{target.id}:FOLLOW_UP:{후속 글 ID}` | 후속 안내 글마다 1번 |
| REPORT_ANSWERED | `{target.type}:{target.id}:ANSWERED:{제보 종류}:{제보 ID}` (제보 종류 `NOTICE`·`AREA`·`BENEFIT`·`PROGRAM`: 생활권 제보는 다른 표라 ID가 겹칠 수 있어서) | 제보마다 1번 |

### 예시

```json
{
  "eventId": "0192b6f0-7c00-7000-8000-000000000101",
  "eventType": "notification.requested",
  "schemaVersion": 1,
  "occurredAt": "2026-10-23T14:10:00Z",
  "producer": "api",
  "payload": {
    "type": "NEW_NOTICE",
    "dedupKey": "NOTICE:0192b6f0-1111-7000-8000-000000000001:NEW",
    "target": { "type": "NOTICE", "id": "0192b6f0-1111-7000-8000-000000000001" },
    "title": "새 공고: 서울 강동구 행복주택 입주자 모집",
    "body": "관심 조건에 맞는 새 공고 소식이에요. SH · 11월 6일 마감",
    "linkPath": "/notices/0192b6f0-1111-7000-8000-000000000001",
    "recipients": [
      { "userId": "0192b6f0-0000-7000-8000-0000000000a1", "email": "a1@example.com", "quietEnabled": false },
      { "userId": "0192b6f0-0000-7000-8000-0000000000a7", "email": null, "quietEnabled": true }
    ]
  }
}
```

`a7`은 이메일을 껐거나 새 공고 알림을 꺼서 `email`이 null이에요. 알림함에는 api가 남기고, 알림 서버는 보내지 않아요.

### 알림 서버가 하는 일

`recipients`의 회원마다, 채널마다 받을 곳이 있으면:
1. `deliveries`에 한 줄 (`dedup_key = {userId}:{dedupKey}`, 같은 채널에 이미 있으면 건너뜀)
2. 보낼 시각(`scheduled_at`)
   - NEW_NOTICE·NEW_SUPPORT: 다음 묶음 시각, `digest = true` (이메일 08:00 또는 18:00, 웹 푸시 30분마다)
   - 나머지: 지금. 단 `quietEnabled`이고 22:00~08:00이면 다음 08:00
3. 워커가 보내고 SENT / 재시도 / FAILED를 남겨요

## 3. `email.verification.requested`

회원이 PWA에서 알림 이메일을 등록하면 api `user` 모듈이 6자리 코드를 만들어(해시만 저장) 보내요. 알림 서버는 **바로** 메일로 보내요 (묶음·조용한 시간 없음).

| 칸 | 모양 | 필수 | 뜻 |
| --- | --- | --- | --- |
| `userId` | uuid | ✅ | |
| `email` | string | ✅ | 인증할 주소 |
| `code` | string | ✅ | 6자리 숫자 |
| `expiresAt` | timestamp | ✅ | 만료 시각 (보통 10분 뒤). 메일에 "14:10까지"로 보여 줘요 |

- 알림 서버는 코드·주소를 저장하지 않아요. 보내지 못하면 로그만 남기고 다시 보내지 않아요 (회원이 "다시 보내기"를 누르면 api가 새 코드로 다시 요청해요)
- 코드 확인(맞는지·5번 제한·만료)은 api가 해요

## 4. `user.withdrawn`

내부 이벤트 `UserWithdrawn`(#54, 이미 발행)을 api user 모듈이 밖으로 보내요.

| 칸 | 모양 | 필수 |
| --- | --- | --- |
| `userId` | uuid | ✅ |

알림 서버는 그 회원의 `deliveries`(안 보낸 줄 포함)를 지워요.

## 5. api가 하는 일 (보내는 쪽 안내)

### 언제, 누구에게 (`notification` 모듈)

| 언제 | 대상자 | type |
| --- | --- | --- |
| `NoticePublished` (reprocess = false) | 주거(`HOUSING`)면 `housing_interests`, 사업공간(`BUSINESS_SPACE`)면 `business_interests`가 맞는 회원 + 그 공고를 관심 공고로 둔 회원 | NEW_NOTICE |
| `BenefitPublished` (reprocess = false) | field `BENEFIT`인 `support_interests`가 맞는 회원 | NEW_SUPPORT |
| `PolicyPublished` (reprocess = false, notice `policy_judgments`에 처음 저장) | 창업지원 사업(`STARTUP_SUPPORT`)·사업공간 모집(`SPACE_RECRUITMENT`)은 `business_interests`가 맞는 회원. 마감됐거나 마감일을 모르는데 상시도 아닌 정책은 보내지 않아요 | NEW_SUPPORT |
| `NoticeUpdated`·`BenefitUpdated`·`PolicyUpdated` (reprocess = false), 알릴 항목이 바뀜 | 관심 공고로 둔 회원 | CORRECTED |
| `NoticeUpdated`에 `followUps` | 관심 공고로 둔 회원 | FOLLOW_UP |
| `ReportAnswered` (공고·혜택·창업 사업·생활권 제보 4종류, 답이 있을 때만) | 제보한 회원 한 명 (테스트 회원은 덧붙이지 않음). 알림 설정으로 끌 수 없고 조용한 시간은 따름. 대상: 공고·생활권 제보 → `NOTICE`(합쳐진 공고면 남은 공고), 혜택 제보 → `BENEFIT`(수집 정책 ID로 benefit `findSummaryByRawPolicyId`, 저장 안 된 혜택이면 보내지 않음), 창업 사업 제보 → `STARTUP_SUPPORT` | REPORT_ANSWERED |
| 매일 11:00 스케줄러 (운영 서버가 낮에만 켜져 있어서) | 마감일이 3일 뒤·1일 뒤인 열린 공고(notice `findOpenClosingOn`)·정책(benefit `findOpenClosingOn`)·창업지원 사업·사업공간 모집(notice `findOpenPoliciesClosingOn`)을 관심 공고로 둔 회원. 하루 한 번(`reminder_runs`), 11:00에 꺼져 있었으면 그날 따라잡기 | DEADLINE_D3·D1 |

### 요청 만들기 순서

1. 대상자 회원 ID 찾기 (user 모듈 조회 메서드, [user-preferences.draft.md](user-preferences.draft.md) 4장)
2. 회원마다 알림 설정·이메일 조회 (user 모듈 `findNotificationContacts(userIds, type)` → `{userId, email | null, quietEnabled}`)
   - `email`은 `email_enabled` + 종류별 설정 켬 + `verified_at` 있음 + `status = ACTIVE`일 때만
3. 문구 만들기 (아래 표) → 알림함(`notification.notifications`)에 회원마다 한 줄 (설정과 상관없이, 같은 dedupKey면 한 번, 90일 보관)
4. 500명씩 `notification.requested`를 아웃박스에 기록. 이메일도 푸시 기기도 없는(또는 이 종류를 끈) 회원은 알림함에만 남고 요청에서 빠져요

- 1~4는 **공고 저장과 같은 트랜잭션**에서 해요 (내부 이벤트를 `@EventListener` 또는 `@TransactionalEventListener(phase = BEFORE_COMMIT)`로 받아요)
- 다른 모듈 데이터는 service 조회 메서드로만 가져와요

### 문구 (api `notification` 모듈이 만들어요)

`{종류}`는 `NOTICE` 공고 · `BENEFIT` 지원 정책 · `STARTUP_SUPPORT` 창업지원 · `SPACE_RECRUITMENT` 사업공간 모집이에요.

| type | title | body |
| --- | --- | --- |
| NEW_NOTICE·NEW_SUPPORT | `새 {종류}: {제목}` | `관심 조건에 맞는 새 {종류} 소식이에요. {기관} · {M월 d일} 마감` |
| DEADLINE_D3 | `마감 3일 전: {제목}` | `관심 {종류} 접수가 {M월 d일}에 마감돼요.` |
| DEADLINE_D1 | `내일 마감: {제목}` | `관심 {종류} 접수가 내일({M월 d일}) 마감돼요.` |
| CORRECTED | `정정: {제목}` | `관심 {종류}의 {일정, 자격} 내용이 바뀌었어요.` (아래 항목 이름) |
| FOLLOW_UP | `후속 안내: {제목}` | `관심 {종류}에 '{후속 글 제목}' ({M월 d일}) 안내가 올라왔어요.` |
| REPORT_ANSWERED | `제보 답변: {대상 제목}` (제목을 모르면 `제보 답변이 도착했어요`) | 고침: `제보하신 '{칸}' 내용을 확인하고 고쳤어요.` · 그대로 둠: `제보하신 '{칸}' 내용을 확인했어요. 원문과 같아 그대로 두었어요.` (생활권은 `생활권 '{칸}'`). **관리자 답변 원문(reply)은 개인정보가 들어갈 수 있어 넣지 않아요** |

메일 앞머리(`[무주택자들]`), 상세 링크, 설정 링크, 묶음 제목("새 소식 3건")은 알림 서버 이메일 채널이 붙여요.

### 알릴 정정 항목

`NoticeUpdated.changedFields`(notice 모듈 `NoticeContent.SECTIONS` + 2개) 중 아래 ✅만 문구에 넣어요. 하나도 없으면 CORRECTED를 보내지 않아요.

| 값 | 뜻 (문구 이름) | 알림 |
| --- | --- | --- |
| `notice` | 기본 정보 | ✅ |
| `schedules` | 일정 | ✅ |
| `supplyGroups` | 공급·가격 | ✅ |
| `eligibility` | 자격 | ✅ |
| `selectionRules` | 선정 방법 | ✅ |
| `requiredDocuments` | 제출 서류 | ✅ |
| `locations` | 위치 | ✅ |
| `guidance` | 안내 문구 | ❌ |
| `followUps` | 후속 안내가 붙음 | CORRECTED가 아니라 FOLLOW_UP으로 |
| `sources` | 다른 출처 공고와 합치기·되돌리기 | ❌ |

### 알릴 정책 정정 항목 (창업지원 사업·사업공간 모집)

`PolicyUpdated.changedFields`는 더 높은 수집 버전이 와서 보이는 값이 바뀐 때만 와요 (같은 버전 승인은 아님). 아래 ✅만 문구에 넣어요.

| 값 | 뜻 (문구 이름) | 알림 |
| --- | --- | --- |
| `basic` | 제목 | ❌ |
| `region` | 지원 지역 | ❌ |
| `schedule` | 신청 기간·상시 여부 (일정) | ✅ |
| `conditions` | 판정 틀의 자격·우대 조건 (자격). 메모(notes)·기준일만 바뀐 것은 넣지 않아요 | ✅ |
| `application` | 원문 주소·문의처·접수 방법 (신청 방법) | ✅ |

### 지역 맞추기 규칙

회원 관심 지역 `R`(5자리), 공고·정책 지역 목록 `T`:
- 공고·정책이 전국(`nationwide` 또는 `regionScope = NATIONWIDE`) → 회원 `include_nationwide`가 true면 맞음
- `T`에 `R`이 있음 → 맞음
- `T`에 `R`의 시도 전체(`R` 앞 2자리 + `000`)가 있음 → 맞음 (경기도 정책 → 성남 회원)
- 회원이 시도 전체(`11000`)를 골랐고 `T`에 같은 시도 시군구가 있음 → 맞음 (주거 공고만)
- `regionScope = UNKNOWN` → 안 맞음 (엉뚱한 알림 방지)

benefit의 시도 코드가 2자리(`11`)면 맞출 때 `11000`으로 바꿔 봐요.

## 6. 나중에: `email.bounced` (알림 서버 → api)

SES 반송(없는 주소)·스팸 신고를 SNS로 받으면 알림 서버가 보내요. api user 모듈이 받아 이메일 `status`를 `BOUNCED`·`COMPLAINED`로 바꾸고, 그 뒤로는 `recipients[].email`에 넣지 않아요.

| 칸 | 모양 | 뜻 |
| --- | --- | --- |
| `userId` | uuid | `deliveries.provider_message_id`로 찾은 회원 |
| `reason` | `BOUNCED` \| `COMPLAINED` | |

알림 서버에도 아웃박스가 필요해요 (SES 연동을 배포할 때).

## 7. 결정과 남은 것

결정 (2026-10-23)

| 결정 | 내용 |
| --- | --- |
| PWA가 부르는 서버 | **api 하나** (B안). 이메일·알림 설정·알림함은 api, 알림 서버는 발송만 |
| 대상자·설정·문구 | api가 정해서 `recipients`·`title`·`body`로 보내요 |
| 인증 코드 메일 | api가 코드를 만들고 `email.verification.requested`로 요청, SES 발송은 알림 서버만 |
| 설정을 바꾸면 | 다음 요청부터 반영해요 (이미 받은 묶음 메일은 그대로 나가요, 최대 10시간) |
| `target.type` | `NOTICE`·`BENEFIT`·`STARTUP_SUPPORT`·`SPACE_RECRUITMENT` 4개 (2026-10-27: 창업지원 사업·사업공간 모집은 notice `policy_judgments`) |
| api 아웃박스·릴레이 | 담당자3이 만들고 담당자1이 리뷰 |
| 후속 안내 | 알려요 (FOLLOW_UP) |

남은 것
1. `BenefitUpdated` 내부 이벤트와 정책 정정 알림 항목 (benefit 저장을 만들 때)
2. 후속 안내 글 제목·ID를 notice 모듈 조회 메서드로 받을 수 있는지 (notice 담당 확인)
3. `email.bounced`와 알림 서버 아웃박스 (배포 전)
