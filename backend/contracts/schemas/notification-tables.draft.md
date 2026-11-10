# 알림 서버 테이블 (초안 v1)

알림 서버(`services/notification`) DB `notification`의 테이블이에요. 첫 채널은 **이메일(AWS SES)**, 웹 푸시는 그다음이에요.

- 저장하는 곳: notification DB (스키마 public), 담당자3
- 받는 이벤트: `notification.requested`, `email.verification.requested`, `user.withdrawn` ([notification-events.draft.md](notification-events.draft.md))
- 마이그레이션: `V202610221630__notification_init.sql`(`processed_events`), `V202610231128__notification_tables.sql`(`deliveries`). 커밋해서 적용된 뒤에는 고치지 말고 새 파일을 만들어요
- **알림 서버는 api가 보낸 대로 보내기만 해요 (2026-10-23 B안).** 회원 이메일·알림 설정·알림함은 api에 있어요 ([user-preferences.draft.md](user-preferences.draft.md)). 여기는 보낼 일과 결과만 둬요

## 1. 테이블 구성

```
deliveries         채널별 발송 1건 = 1줄. 보낼 곳·문구·보낼 시각·재시도·결과
processed_events   받은 이벤트 장부 (같은 이벤트 두 번 처리 방지). 90일 지나면 deliveries와 같이 지워요
```

## 2. `deliveries`

`notification.requested`의 `recipients` 1명 × 받을 곳이 있는 채널 1개마다 한 줄이에요.

| 칸 | 모양 | 뜻 |
| --- | --- | --- |
| `id` | uuid PK | UUID v7 |
| `user_id` | uuid | api `users.id` (다른 DB라 FK 없음) |
| `channel` | `EMAIL` \| `PUSH` | |
| `address` | text \| null | 보낼 곳 (이메일 주소, 웹 푸시는 구독 기기 목록). **끝나면(SENT·FAILED) 지워요** |
| `type` | text | `NEW_NOTICE` · `NEW_SUPPORT` · `DEADLINE_D3` · `DEADLINE_D1` · `CORRECTED` · `FOLLOW_UP` |
| `dedup_key` | text | `{user_id}:{요청의 dedupKey}`. `unique (dedup_key, channel)`이라 같은 요청이 다시 와도 두 번 보내지 않아요 |
| `title`, `body`, `link_path` | text | api가 만든 문구와 PWA 화면 경로 |
| `digest` | boolean | 묶음 메일로 보낼 건 (새 공고·새 정책 이메일) |
| `quiet` | boolean | 회원이 조용한 시간을 켰나 (요청 때 값) |
| `status` | text | `PENDING` → `SENT` / `FAILED`(영구 실패 또는 재시도 다 씀) |
| `scheduled_at` | timestamptz | 보낼 시각 |
| `attempts` | int | |
| `last_error` | text \| null | SES 오류 코드 (주소는 넣지 않아요) |
| `provider_message_id` | text \| null | SES MessageId. 반송 알림(SNS)이 오면 어떤 회원인지 찾아요. 묶음 메일은 같은 값 |
| `sent_at` | timestamptz \| null | |
| `created_at` | timestamptz | 90일 지나면 지워요 |

**탈퇴 회원 기록 (`withdrawn_users`)**: `user_id` PK, `withdrawn_at`. `user.withdrawn`을 받을 때 발송 줄을 지우면서 넣어요. 탈퇴 전에 만든 `notification.requested`가 재시도로 늦게 와도 그 회원 줄은 만들지 않아요. 90일 지나면 지워요 (04:00 정리 작업)

**보낼 시각 (`scheduled_at`)**
- `NEW_NOTICE`·`NEW_SUPPORT`: `digest = true`, 채널의 다음 묶음 시각 (Asia/Seoul)
  - 이메일: 08:00 또는 18:00. 두 시각 모두 조용한 시간 밖이에요
  - 웹 푸시: 다음 정각 또는 30분. `quiet`이고 22:00~08:00이면 다음 08:00 ([web-push.draft.md](web-push.draft.md) 4장)
- 나머지: 지금. `quiet`이고 22:00~08:00이면 다음 08:00
- 재시도: 실패하면 `attempts`를 올리고 뒤로 미뤄요 (1분 → 5분 → 30분, 그다음은 FAILED). 재시도가 밤으로 밀리면 보내기 직전에 다시 08:00으로 미뤄요

**발송 워커**
- **맡기 → 보내기 → 결과** (2026-10-26). 바깥 서비스(푸시 서비스·SES)를 기다리는 동안 DB 잠금을 쥐지 않아요
  1. 맡기 (짧은 트랜잭션): 보낼 차례인 줄을 `for update skip locked`로 골라 `locked_until = now + 10분`을 적어요. 다른 서버는 `locked_until`이 지나지 않은 줄을 건너뛰어요 (서버 여러 대여도 같은 건을 두 번 안 보내요). 조용한 시간이면 맡지 않고 08:00으로 미뤄요
  2. 보내기 (트랜잭션 밖): 웹 푸시는 기기마다 동시에 보내요
  3. 결과 (줄마다 짧은 트랜잭션): SENT·재시도·FAILED를 적고 `locked_until`을 지워요
  - 보내고 결과를 적기 전에 서버가 죽으면 10분 뒤 다른 서버가 다시 보내요 (드물게 한 번 더 갈 수 있어요: 최소 한 번)
  - 죽은 푸시 구독 이벤트(`push.subscription.expired`)는 자기 트랜잭션으로 바로 아웃박스에 적어요 (결과 기록이 실패해도 기기가 죽은 것은 사실)
- `digest = true`는 같은 회원·같은 주소·같은 `scheduled_at` 건을 메일 1통("관심 조건에 맞는 새 소식 3건")으로 보내고 모두 `SENT` + 같은 `provider_message_id`
- 묶는 이유: 메일 여러 통에 지친 사용자의 스팸 신고가 쌓이면 SES 발송이 정지돼 모든 회원의 메일이 멈춰요. 웹 푸시는 폰이 연달아 울려 사용자가 권한을 꺼 버리지 않게 30분씩 묶어요 (같은 회원·`PUSH`·같은 `scheduled_at`, 기기 목록은 가장 늦은 줄 것)
- SES 초당 발송 한도(샌드박스 1통)를 넘지 않게 간격을 둬요
- 보낼지 말지(회원 설정)는 api가 이미 정했어요. 워커는 다시 따지지 않아요

**지우기**
- `user.withdrawn`: 그 회원의 줄을 모두 지워요 (안 보낸 줄 포함)
- 90일 지난 줄은 매일 04:00(Asia/Seoul)에 1,000줄씩 나눠 지워요. 아직 안 보낸 줄(PENDING)은 남겨요 (`DeliveryPurgeJob`)

## 3. 인증 코드 메일

`email.verification.requested`는 `deliveries`에 남기지 않고 바로 보내요. 회원이 화면에서 기다리고 있고, 코드를 DB에 남기지 않으려고요. 실패하면 로그만 남기고, 회원이 "다시 보내기"를 누르면 api가 새로 요청해요.

## 4. 결정 (2026-10-23)

| 결정 | 내용 |
| --- | --- |
| B안 | 회원 이메일·알림 설정·알림함은 api. 예전 초안의 `notification_settings`·`email_addresses`·`notifications`는 api로 옮겼어요 |
| 주소 보관 | 보내는 동안만 `deliveries.address`, 끝나면 지워요 |
| 발송 기록 보관 | 90일 |
| 새 공고 메일 묶음 | 새 공고·새 정책 이메일은 하루 두 번(08:00·18:00) 묶음, 마감·정정·후속 안내는 바로 |
| 웹 푸시 | 채널(`PushChannel`)만 추가. 구독 정보는 api가 저장하고 요청에 넣어 보내요. `address`는 남은 기기 목록이라 재시도는 못 받은 기기에만 ([web-push.draft.md](web-push.draft.md) 4장) |
