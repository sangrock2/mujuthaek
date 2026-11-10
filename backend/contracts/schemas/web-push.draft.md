# 웹 푸시 계약 (초안 v1)

이메일 대신 **웹 푸시**로 알림을 보내기 위한 약속이에요. 이메일 코드는 그대로 두고, 푸시를 채널 하나로 더해요.
[notification-events.draft.md](notification-events.draft.md)의 B안(PWA는 api만 부름, api가 "누구에게·어디로·무엇을", 알림 서버는 "언제·어떻게")을 그대로 따라요.

- 상태: **초안**이에요. 8장에 정한 것과 남은 것을 적었어요. 남은 것을 정한 뒤 `contracts/events/*.v1.json`과 api 문서로 옮겨요
- 표준: Web Push(RFC 8030), VAPID(RFC 8292), 내용 암호화 `aes128gcm`(RFC 8291). 브라우저마다 따로 만들 것 없이 같은 코드로 보내요

```
① PWA  "알림 받기" 버튼 → 권한 허용 → pushManager.subscribe(VAPID 공개키)
        → 브라우저가 구독 정보 {endpoint, p256dh, auth}를 만들어 줌
② PWA → api   PUT /api/users/me/push-subscriptions (기기마다 1줄 저장)
③ api  알림 요청을 만들 때 recipients[].push에 그 회원의 기기 목록을 넣음 → 아웃박스 → 알림 서버
④ 알림 서버  기기마다 endpoint로 암호화한 내용을 보냄 (VAPID 개인키로 서명)
        → 브라우저 회사의 푸시 서비스 (Google·Mozilla·Apple) → 기기
⑤ PWA 서비스 워커  push 이벤트 → 알림 띄움 → 누르면 linkPath 화면 열기
⑥ 죽은 구독(404·410)  알림 서버 → api   push.subscription.expired → api가 그 줄을 지움
```

## 1. 저장하는 것

### 1-1. api: 구독 기기 `notification.push_subscriptions` (기기마다 1줄)

| 칸 | 모양 | 뜻 |
| --- | --- | --- |
| `id` | uuid PK | UUID v7 |
| `user_id` | uuid | 회원. user 모듈 테이블을 직접 참조하지 않아요(FK 없음). 탈퇴는 `UserWithdrawn`으로 지워요 |
| `endpoint` | text **unique** | 이 기기로 가는 주소 (브라우저가 만듦). 최대 2,048자 |
| `p256dh` | text | 내용을 그 기기만 열 수 있게 잠그는 공개키 (브라우저가 만듦) |
| `auth` | text | 암호화에 같이 쓰는 비밀값 (브라우저가 만듦) |
| `user_agent` | text \| null | "갤럭시 Chrome"처럼 기기 목록에 보여 줄 이름 (최대 200자) |
| `created_at`, `updated_at` | timestamptz | 처음 등록, 마지막 등록(같은 기기가 다시 보냄) |

- **notification 모듈에 둬요.** 로그인·계정 정보가 아니라 "알림을 보낼 기기 주소"이고, 읽는 곳(요청 만들기)과 지우는 곳(`push.subscription.expired`)이 모두 notification이에요. dev의 `notification` 모듈 설명도 "웹 푸시 알림 모듈"이에요
- 회원 한 명당 **최대 5대**. 6번째를 등록하면 `updated_at`이 가장 오래된 기기를 지워요 (브라우저 데이터 삭제·재설치 때마다 쌓이는 죽은 구독, 커지는 요청, 가짜 구독 대량 등록을 막아요)
- `endpoint`·`p256dh`·`auth`는 **알면 그 기기에 알림을 보낼 수 있는 값**이라 비밀번호처럼 다뤄요. 로그·오류 응답에 넣지 않아요 (로그에는 `userId`와 주소의 도메인 `fcm.googleapis.com` 정도만)

### 1-2. 켬·끔: 따로 `push_enabled`를 두지 않아요

- **이 기기에 구독이 있으면 켜짐, 없으면 꺼짐**이에요. 기기에서 "알림 받기"를 켜는 것(권한 허용 → 구독 `PUT`) 자체가 켜는 거예요
  - 설정값과 구독이 어긋나는 상태("기기는 있는데 설정이 꺼짐", "설정은 켰는데 기기가 없음")가 생기지 않아요
  - 한 번 권한을 허용한 브라우저는 다시 켤 때 권한 창 없이 바로 다시 구독돼요
- 기기 하나 끄기 = 그 기기 구독 지우기. 모든 기기 끄기 = 내 구독 모두 지우기 (2장)
- 계정 설정에는 **어떤 알림을 받을지**만 둬요: 종류별 켬·끔, `quiet_enabled` ([user-preferences.draft.md](user-preferences.draft.md), 이메일과 같이 써요)
- [user-preferences.draft.md](user-preferences.draft.md)의 `notification_settings`에는 푸시 켬·끔 칸이 없어요
- 사용자가 브라우저 설정에서 권한을 끄면: 다음 발송 때 404·410을 받아 구독이 지워지고(5장), PWA는 앱을 열 때 `Notification.permission`을 보고 토글을 맞춰요

### 1-3. 서버 설정: VAPID 키 한 쌍 (서비스 전체에 1개)

| 이름 | 누가 | 뜻 |
| --- | --- | --- |
| `PUSH_VAPID_PUBLIC_KEY` | api(PWA에 줌) · 알림 서버 | "이 서비스에서 오는 알림만 받을게" |
| `PUSH_VAPID_PRIVATE_KEY` | **알림 서버만** | 보낼 때 서명. **커밋하지 않고 `.env`·배포 비밀값에만** |
| `PUSH_VAPID_SUBJECT` | 알림 서버 | 연락처 (`mailto:팀 주소` 또는 서비스 주소). 푸시 서비스가 문제 있을 때 연락해요 |

- 만들기: `npx web-push generate-vapid-keys` (한 번만)
- **키를 바꾸면 모든 구독이 무효**가 돼요. 바꿀 일이 생기면 PWA가 새 키로 다시 구독하게 해야 해요

### 1-4. 알림 서버: 따로 저장하지 않아요

보내는 동안만 `deliveries.address`에 기기 목록을 두고, 끝나면(SENT·FAILED) 지워요 (이메일 주소와 같은 규칙).

구독 정보는 **api가 요청에 실어 보내요** (B안 그대로). 알림 서버에 구독 사본을 두지 않아서 등록·해제를 맞출 이벤트가 필요 없고, 정답은 api 한 곳에만 있어요. 대신 이렇게 정해요:
- 기기 목록은 **요청을 만든 시점**의 것이에요. 조용한 시간·묶음으로 늦게 보내면 그 사이 해제한 기기에도 한 번 갈 수 있어요 (드문 일이라 받아들여요)
- 키는 아웃박스·RabbitMQ·실패 큐·`deliveries`를 지나가요. 로그에는 남기지 않고, 발송이 끝나면 `deliveries`에서 지워요

## 2. api HTTP (PWA가 불러요, api `notification` 모듈)

로그인이 필요한 요청은 다른 회원 API처럼 `/api/users/me/…` 아래에 둬요 (SecurityConfig가 `/api/users/**`를 로그인한 회원만 받아요).

| 요청 | 로그인 | 하는 일 | 응답 |
| --- | --- | --- | --- |
| `GET /api/v1/push/public-key` | 필요 없음 | VAPID 공개키 | `200 {"publicKey": "BEl6…"}`. 서버에 설정이 없으면 `503 PUSH_NOT_CONFIGURED` |
| `PUT /api/users/me/push-subscriptions` | 필요 | 이 기기 등록·갱신. 같은 `endpoint`가 있으면 내용·`updated_at`을 바꾸고, **다른 회원의 것이면 지금 회원으로 옮겨요**(같은 브라우저에서 다른 계정으로 로그인) | `204` |
| `DELETE /api/users/me/push-subscriptions` | 필요 | 이 기기 해제 (이 기기 알림 끄기, **로그아웃 직전**). 본문 없이 `?scope=all`이면 **내 기기 모두** 해제 (설정 화면 "모든 기기 알림 끄기") | `204` (없어도 204) |
| `GET /api/users/me/push-subscriptions` | 필요 | 내 기기 목록 (`id`, `userAgent`, `createdAt`, `updatedAt`), 최근에 쓴 기기부터. `endpoint`·키는 주지 않아요 | `200 [...]` |
| `DELETE /api/users/me/push-subscriptions/{id}` | 필요 | 목록에서 다른 기기 해제 | `204` / 남의 기기면 `404 PUSH_SUBSCRIPTION_NOT_FOUND` |

`PUT`·`DELETE` 본문 (브라우저 `subscription.toJSON()` 모양 그대로):

```json
{
  "endpoint": "https://fcm.googleapis.com/fcm/send/dX3k…",
  "keys": { "p256dh": "BNcRd…", "auth": "tBHI…" },
  "userAgent": "Chrome / Android"
}
```

- `DELETE`는 `endpoint`만 있어도 돼요. 모두 해제할 때(`?scope=all`)는 본문이 없어요
- 모두 해제한 뒤 이 기기에서 다시 켜면 PWA가 `PUT`만 다시 하면 돼요 (권한은 그대로라 창이 뜨지 않아요)
- 검사 (틀리면 `400 VALIDATION_FAILED`, 오류 문구에는 칸 이름만 넣고 값은 넣지 않아요)
  - `endpoint`: `https://`, 포트·사용자 정보 없음, 2,048자 이하, **푸시 서비스 도메인**(`fcm.googleapis.com`, `*.push.services.mozilla.com`, `*.push.apple.com`, `*.notify.windows.com`, 설정 `app.push.allowed-hosts`). 알림 서버가 이 주소로 요청을 보내서, 아무 주소나 받으면 우리 서버가 남의 서버를 부르게 돼요
  - `p256dh`: base64url, 풀면 65바이트 / `auth`: base64url, 풀면 16바이트 (패딩 `=`은 있어도 돼요)
  - `userAgent`: 없어도 돼요. 200자를 넘으면 잘라요
- 탈퇴 뒤 남은 access token(최대 30분)으로 `PUT`하면 401이에요 (`WithdrawnUserFilter`가 쓰기 요청을 막아요). 지운 기기가 다시 생기지 않아요
- PWA는 **앱을 열 때마다** 현재 구독을 `PUT`해요 (브라우저가 구독을 몰래 바꾼 경우를 맞추고, `updated_at`이 "최근에 쓴 기기"가 돼요)

## 3. `notification.requested`에 더하는 칸

| 칸 | 모양 | 필수 | 뜻 |
| --- | --- | --- | --- |
| `recipients[].push` | object[] \| null | 아니요 (없으면 null) | 보낼 기기 목록, 최근에 쓴 기기부터 최대 5대. 이 종류를 켠 회원만 받는 사람으로 고르고(이메일과 같은 종류별 켬·끔), 그 회원에게 기기가 있으면 넣어요. 없으면 null |
| `recipients[].push[].endpoint` | string | ✅ | |
| `recipients[].push[].p256dh` | string | ✅ | |
| `recipients[].push[].auth` | string | ✅ | |

```json
"recipients": [
  {
    "userId": "0192b6f0-0000-7000-8000-0000000000a1",
    "email": null,
    "quietEnabled": true,
    "push": [
      { "endpoint": "https://fcm.googleapis.com/fcm/send/dX3k…", "p256dh": "BNcRd…", "auth": "tBHI…" },
      { "endpoint": "https://web.push.apple.com/QGl4…", "p256dh": "BLc2…", "auth": "k9Qe…" }
    ]
  }
]
```

- `email`과 `push`가 둘 다 null인 회원은 알림함에만 남아요 (알림 서버는 아무것도 안 보내요)
- 칸을 더하는 것이라 `schemaVersion`은 `1` 그대로예요. 지금 알림 서버는 모르는 칸을 조용히 무시해서(`NotificationRequest.Recipient`에 `push`가 없음) 먼저 넣어도 깨지지는 않지만 푸시가 나가지 않아요. 그래서 **알림 서버(`PushChannel`)를 먼저 배포**한 뒤 api가 `push`를 넣기 시작해요
- api는 아웃박스에 적을 때 500명 묶음마다 한 번 조회해서 기기를 붙여요 (`NotificationRequests`). 받는 사람을 고르는 쪽(`RecipientFinder`)은 기기를 몰라도 돼요
- 크기: 500명 × 5대면 요청 하나가 1MB 안팎이에요. 아웃박스 줄은 보낸 지 하루 뒤 지워져서 키가 오래 남지 않아요 (`OutboxCleanup`). 실패 큐(.dlq)로 간 메시지에는 남아 있어서, 실패 큐를 볼 때도 키를 밖에 옮기지 않아요
- 문구 길이: 푸시 내용은 암호화 뒤 4KB가 한계라, api가 `title` 100자·`body` 200자를 넘으면 잘라서 끝에 `…`을 붙여요 (이메일·알림함도 같은 문구)

## 4. 알림 서버가 보내는 방법 (`PushChannel`)

`NotificationChannel`을 구현한 빈 하나예요. 발송 줄·중복 거르기·조용한 시간·재시도는 지금 것을 그대로 써요.

### 발송 줄

- 회원 1명 × 채널 1개 = `deliveries` 1줄 (지금과 같음). `address`에는 기기 목록 JSON
- 한 줄 안에서 기기마다 보내고, **성공하거나 죽은 기기는 `address`에서 빼요.** 재시도는 남은 기기에만 해서, 이미 받은 기기가 두 번 받지 않아요

### 보낼 시각

| 종류 | 보낼 시각 |
| --- | --- |
| `DEADLINE_D3`·`DEADLINE_D1`·`CORRECTED`·`FOLLOW_UP` (내 관심 공고) | 바로. `quietEnabled`이고 22:00~08:00이면 다음 08:00 |
| `NEW_NOTICE`·`NEW_SUPPORT` (새 소식) | **30분 묶음**: 다음 정각 또는 30분(Asia/Seoul, 예: 10:07 → 10:30, 10:30 → 10:30). 그 시각이 조용한 시간이고 `quietEnabled`이면 다음 08:00 |

- 새 소식이 한꺼번에 많은 날(수집기 한 회차에 LH·SH 공고 여러 건, 밤새 쌓인 것이 08:00에)에 폰이 연달아 울리면 사용자가 권한을 꺼 버리고, 그러면 **D-1 마감 알림까지 못 받아요.** 그래서 새 소식만 모아요. 늦어도 30분이에요
- 칸으로는 이메일 묶음과 같아요: `digest = true` (`PushChannel.supportsDigest() = true`). 묶음 시각만 채널마다 달라요 (이메일 08:00·18:00, 푸시 30분마다). 지금 `DeliverySchedule.firstAttempt`가 묶음 시각을 하나로 정해 두어서, 채널이 다음 묶음 시각을 정하게 바꿔요
- 묶는 단위: **같은 회원 · `PUSH` · 같은 `scheduled_at`** 줄들. 기기 목록(`address`)은 요청마다 다를 수 있어서(그 사이 기기 등록·해제) 같은 주소로 묶지 않고, **가장 늦게 만든 줄의 기기 목록**으로 보내요
- 묶인 줄은 결과를 같이 써요: 모두 SENT, 또는 같이 재시도·FAILED. 재시도하면 묶음이 쪼개지지 않게 모두 같은 `scheduled_at`으로 미뤄요 (이메일 묶음과 같은 규칙)
- 1건뿐이면 묶음 문구 없이 그 건 그대로 보내요

### 기기에 보내는 내용 (서비스 워커가 `event.data.json()`으로 받음)

```json
{
  "v": 1,
  "type": "DEADLINE_D1",
  "title": "내일 마감: 서초구 서리풀 청년아트타운 잔여세대 입주자 모집공고",
  "body": "관심 공고 접수가 내일(10월 30일) 마감돼요.",
  "linkPath": "/notices/0192b6f0-1111-7000-8000-000000000001",
  "tag": "/notices/0192b6f0-1111-7000-8000-000000000001",
  "ids": ["0192b6f0-2222-7000-8000-000000000001"]
}
```

- `ids`: api 알림함 줄 ID (묶음이면 묶인 알림 모두). 서비스 워커는 알림을 띄우면 `POST /api/v1/notifications/{id}/shown`, 누르면 `POST /api/v1/notifications/{id}/clicked`로 알려요 (로그인 없이, 늘 204). 관리자 「알림」 화면의 봤는지·눌렀는지 지표예요
- `tag`: 같은 화면(공고) 알림은 기기에서 **최신 것 하나로 바꿔 보여요** (D-3 뒤 정정이 오면 정정만 남음). `linkPath`와 같은 값이에요

새 소식 묶음(2건 이상)은 알림 서버가 문구를 만들어요:

```json
{
  "v": 1,
  "type": "NEW_DIGEST",
  "title": "새 소식 3건",
  "body": "서초구 서리풀 청년아트타운 잔여세대 입주자 모집공고 외 2건",
  "linkPath": "/notifications",
  "tag": "/notifications"
}
```

- `body`는 가장 먼저 만든 건의 제목(앞의 "새 공고: " 같은 머리말은 빼요) + " 외 N건"이에요. 200자를 넘으면 제목을 잘라요
- 누르면 알림함(`/notifications`)으로 가요. 여러 건이라 한 공고로 보낼 수 없어서예요
- `tag`가 같아서 다음 묶음이 오면 기기에는 최신 묶음 하나만 보여요 (전에 온 묶음의 내용은 알림함에 그대로 있어요)
- `NEW_DIGEST`는 기기로 가는 내용에만 쓰는 값이에요. `notification.requested`의 `type`에는 없어요

### 함께 보내는 헤더

| 헤더 | 값 | 뜻 |
| --- | --- | --- |
| `TTL` | `DEADLINE_D1` 12시간 · `DEADLINE_D3` 48시간 · `NEW_*`·묶음 24시간 · `CORRECTED`·`FOLLOW_UP` 72시간 | 기기가 꺼져 있을 때 푸시 서비스(Google·Mozilla·Apple)가 이 알림을 얼마나 들고 있을지. 지나면 버려요 (늦게 받으면 틀린 말이 되는 마감 알림은 짧게). 정하지 않으면 라이브러리 기본값 4주예요 |
| `Urgency` | `DEADLINE_D1` `high` · 나머지 `normal` | 배터리 절약 모드에서도 바로 보낼지 |
| `Content-Encoding` | `aes128gcm` | 표준 암호화 |
| `Authorization` | `vapid t=…, k=…` | VAPID 서명 (라이브러리가 만듦) |

### 푸시 서비스의 답과 처리

| 답 | 뜻 | 처리 |
| --- | --- | --- |
| `201` | 받음 | 그 기기 완료 |
| `404`·`410` | **죽은 구독** (앱 삭제·권한 끔·만료) | 그 기기 빼고 `push.subscription.expired` (5장). 다시 보내지 않아요 |
| `429` | 너무 많이 보냄 | 그 기기만 `Retry-After`(초)만큼 뒤에 다시. 정한 재시도 간격보다 짧으면 정한 간격, 최대 하루 |
| `5xx`·시간 초과·연결 실패 | 푸시 서비스 문제 | 그 기기만 지금 재시도 규칙대로 다시 |
| `400`·`413` | 우리 쪽 잘못 (형식·크기) | 다시 보내지 않고 FAILED, `last_error`에 코드 |
| `401`·`403` | VAPID 키 문제 (설정 오류) | 다시 보내지 않고 FAILED, **경고 로그** (모든 발송이 실패하는 상황이라 바로 알아야 해요) |

- 줄 상태: 남은 기기가 없으면 SENT (한 대라도 받았으면 SENT, 모두 죽었으면 FAILED `ALL_EXPIRED`)
- 알림 서버도 보내기 전에 받을 곳을 다시 확인해요 (https, 푸시 서비스 도메인 `notification.push.allowed-hosts`). 아니면 그 기기는 보내지 않고 `PUSH_ENDPOINT_NOT_ALLOWED`. 리다이렉트(3xx)는 따라가지 않아요
- 내용(암호화 전 JSON)은 3,993바이트까지예요 (암호화하면 4,096바이트). 넘으면 FAILED `PUSH_PAYLOAD_TOO_LARGE`
- 암호화(RFC 8291)·VAPID 서명(RFC 8292)은 JDK 기본 암호 기능으로 직접 해요 (RFC 8291 부록 A 예제와 같은 결과인지 테스트). VAPID 토큰은 12시간짜리, `aud`는 푸시 서비스 주소의 앞부분(`https://fcm.googleapis.com`)
- 로그에는 `userId`·`deliveryId`·푸시 서비스 도메인·응답 코드만 남겨요

## 5. 새 이벤트 `push.subscription.expired` (알림 서버 → api)

| 칸 | 모양 | 필수 | 뜻 |
| --- | --- | --- | --- |
| `userId` | uuid | ✅ | |
| `endpoint` | string | ✅ | 죽은 기기 주소 |
| `status` | int | ✅ | `404` 또는 `410` |

- api `notification` 모듈이 받아 `user_id`·`endpoint`가 모두 같은 줄만 지워요 (그 사이 다른 회원으로 옮겨진 기기는 안 지움)
- 봉투 `producer`는 `notification`, 라우팅 키는 `push.subscription.expired`. 알림 서버 아웃박스(`outbox`)에 발송 결과와 같은 트랜잭션으로 적고, 릴레이가 1초마다 `mujuthaek.events`로 보내요 (보낸 줄은 하루 뒤 삭제)
- api 받는 큐: `mujuthaek.api.push-subscription-expired` (+ `.dlq`). 같은 eventId는 한 번만, `userId`·`endpoint`가 없으면 실패 큐로
- 묶음·재시도 중이던 다른 기기는 영향이 없어요. 이 이벤트가 api에 닿기 전에 만든 요청에는 그 기기가 또 들어 있을 수 있어서, 그때는 다시 410을 받고 또 알려요 (같은 결과, 문제없음)

## 6. 탈퇴·로그아웃

| 언제 | api | 알림 서버 |
| --- | --- | --- |
| 탈퇴 (`UserWithdrawn`) | 그 회원 구독을 모두 지움 (같은 트랜잭션) | `user.withdrawn`으로 발송 줄 지움 (주소 포함) |
| 로그아웃 | PWA가 로그아웃 **전에** `DELETE /push/subscriptions` | — |
| 같은 브라우저에서 다른 계정 로그인 | `PUT`이 구독을 새 회원으로 옮김 | — |

- 탈퇴 전에 만든 요청이 늦게 도착할 수 있어요 (아웃박스 재시도 순서). 알림 서버는 `user.withdrawn`을 받으면 **탈퇴한 회원 ID를 `withdrawn_users`에 90일 기억**하고, 그 뒤에 온 요청에서 그 회원을 걸러요

## 7. 브라우저별 차이 (프론트가 챙길 것)

서버 쪽은 브라우저와 상관없이 같아요. `endpoint` 도메인만 달라요.

| 브라우저 | `endpoint` 도메인 | 챙길 것 |
| --- | --- | --- |
| Chrome·Edge·삼성 인터넷 (Android·PC) | `fcm.googleapis.com` 등 | 큰 이미지·버튼은 되지만 쓰지 않아요 (모두 같게) |
| Firefox | `updates.push.services.mozilla.com` | 권한은 버튼을 눌렀을 때만 물을 수 있어요 |
| Safari (Mac) | `web.push.apple.com` | 위와 같음 |
| **iPhone·iPad** (iOS·iPadOS 16.4+) | `web.push.apple.com` | **홈 화면에 추가한 PWA에서만** 돼요. 그냥 Safari로 열면 "홈 화면에 추가해 주세요" 안내 |

모든 브라우저 공통:
- HTTPS 필요 (로컬 `localhost`는 예외)
- 권한은 **"알림 받기" 버튼을 누를 때** 물어요 (페이지를 열자마자 물으면 막히거나 거절이 많아요)
- 푸시를 받으면 **반드시 알림을 띄워요** (`userVisibleOnly: true`). 조용히 받기만 하면 브라우저가 권한을 거둬요
- 제목·본문·아이콘만 써요

서비스 워커가 할 일: `push`(알림 띄우기, `ids`로 shown 알리기), `notificationclick`(그 `linkPath` 열기, 이미 열린 탭이 있으면 그 탭으로, `ids`로 clicked 알리기), `pushsubscriptionchange`(새 구독을 `PUT`).

## 8. 정한 것과 남은 것

**정한 것 (2026-10-26)**

| 항목 | 정한 것 | 자세히 |
| --- | --- | --- |
| 구독 테이블 위치 | api `notification` 모듈 (`notification.push_subscriptions`) | 1-1 |
| 구독 정보 | 요청에 실어 보내요 (B안 유지). 알림 서버는 구독을 저장하지 않아요 | 1-4, 3장 |
| 켬·끔 | `push_enabled` 없음 (user-preferences에서도 뺌). 구독이 있으면 켜짐, 모두 끄기 = 내 구독 모두 지우기 | 1-2, 2장 |
| 새 소식이 많은 날 | `NEW_*`만 30분 묶음, 2건 이상이면 "새 소식 N건" 한 번. 내 관심 공고 알림은 바로 | 4장 |
| 회원당 기기 수 | 5대. 넘으면 `updated_at`이 가장 오래된 기기를 지워요 | 1-1 |
| TTL 값 | `DEADLINE_D1` 12시간 · `DEADLINE_D3` 48시간 · `NEW_*`·묶음 24시간 · `CORRECTED`·`FOLLOW_UP` 72시간 | 4장 |

**남은 것**

| 항목 | 제안 |
| --- | --- |
| 이메일 | 코드는 두고, 운영에서는 이메일 칸을 null로 (나중에 정리) |
