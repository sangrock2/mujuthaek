# api (자바 25 + 스프링 부트, 모듈러 모놀리스)

```
src/main/java/kr/mujuthaek/api/
├─ ApiApplication.java
├─ common/          event/ · dto/response/ · exception/ · pagination/ · config/   (업무 규칙 없음)
├─ notice/          공고                     ┐
├─ benefit/         혜택·창업지원            │  모듈마다: controller · service · repository · domain ·
├─ eligibility/     판정·준비할 돈 (+ rule/) │           model(필요할 때) · dto/request · dto/response ·
├─ area/            생활권·상권              │           mapper · event
├─ user/            로그인·관심 (account)    │
└─ notification/    사용자 알림·웹 푸시      ┘
```

## 규칙 요약
- 다른 모듈 데이터는 서비스 계층에서 그 모듈 서비스의 **조회 메서드**로. 한 방향으로만, record로만
- 다른 모듈의 repository·테이블은 쓰지 않음. 다른 모듈에 영향을 주는 변경은 `common/event` 이벤트로
- 각 모듈의 `service` 패키지만 공개(`@NamedInterface`). `ModuleStructureTest`가 경계와 순환을 검사

자세한 규칙은 저장소 루트의 `CLAUDE.md`와 팀 컨벤션 문서를 봐요.

## 실행
```bash
./gradlew spotlessApply       # 포맷 맞추기
./gradlew check               # 포맷 검사 + 테스트 (모듈 경계 포함)
./gradlew bootRun             # 실행 (DB·RabbitMQ는 infra에서 먼저 띄우기)
```

## 로그인 (user 모듈)
카카오·네이버·구글 소셜 로그인 + JWT예요. 제공자를 더 붙이려면 `application.yml`의 registration과 `SocialProfiles`에 추가해요.

| 토큰 | 유효 | 어디에 | 쓰임 |
| --- | --- | --- | --- |
| access token (JWT, HS256) | 30분 | 프론트 메모리 | 요청마다 `Authorization: Bearer <토큰>`. 서버에 저장하지 않아요 |
| refresh token | 14일 | HttpOnly 쿠키 `refresh_token` (Path=/api/auth, SameSite=Lax, 운영 Secure) | access token 재발급. DB(`account.refresh_tokens`)에는 SHA-256 해시만 |

| 동작 | 주소 | 비고 |
| --- | --- | --- |
| 로그인 시작 | `GET /oauth2/authorization/{kakao\|naver\|google}` | 제공자 동의 화면으로 이동. 끝나면 refresh token 쿠키를 받고 `FRONTEND_URL/`로, 실패하면 `FRONTEND_URL/login?error=social&reason=…`로 돌아가요 |
| 콜백 | `GET /login/oauth2/code/{kakao\|naver\|google}` | 각 개발자 콘솔에 Redirect(Callback) URI로 등록 (스프링 필터가 처리, 컨트롤러 없음) |
| access token 받기·재발급 | `POST /api/auth/refresh` | 쿠키로 확인. `{accessToken, tokenType: "Bearer", expiresIn}` + 새 refresh token 쿠키 (회전: 쓴 값은 다시 못 써요). 실패하면 401 `INVALID_REFRESH_TOKEN` → 다시 로그인. 같은 쿠키로 동시에 부르면 먼저 온 하나만 새 토큰을 받고 나머지는 409 `CONFLICT`(쿠키는 그대로) → 원래 요청을 한 번 다시. `Authorization` 헤더는 읽지 않아요(만료된 access token이 붙어 와도 막히지 않게) |
| 내 정보 | `GET /api/users/me` | Bearer 없거나 만료면 401 `UNAUTHORIZED` |
| 연락용 이메일 등록·변경 | `PUT /api/users/me/email` | 선택 항목. 본문 `{email, consentVersion}`(화면이 보여 준 동의 문구 버전, 예 `email-v1`). 204. 가입 마무리 화면과 마이페이지가 같이 써요. 형식이 틀리면 400 `VALIDATION_FAILED`(주소는 응답·로그에 넣지 않아요). 다른 회원이 쓰는 주소면(대소문자 무시) 409 `EMAIL_ALREADY_USED`, 본인이 같은 주소로 다시 저장하는 건 돼요. 인증 코드는 받지 않아요. 등록한 주소는 `GET /api/users/me`의 `email`(없으면 null) |
| 연락용 이메일 삭제 | `DELETE /api/users/me/email` | 동의 철회. 주소와 동의 기록(버전·시각)을 같이 지워요. 없어도 204 |
| 로그아웃 | `POST /api/auth/logout` | 이 기기의 refresh token 삭제 + 쿠키 삭제, 204 |
| 탈퇴 시작 | `POST /api/users/me/withdrawal[?provider=naver]` | 바로 지우지 않고 `{provider, reauthUrl, expiresIn, otherProviders}`를 줘요. `otherProviders`(함께 연결된 다른 소셜)는 서버가 연결을 끊을 수 없어서, 탈퇴 전에 "각 서비스에서 직접 해제하세요"라고 보여 줘요. 프론트가 `reauthUrl`로 **페이지 이동** → 그 소셜로 다시 로그인 → 회원 삭제(hard delete) → 소셜 연결 끊기 → `FRONTEND_URL/withdrawn`. 실패·취소는 `FRONTEND_URL/mypage?withdraw=cancelled\|expired\|account_mismatch\|failed` |

프론트 순서: 로그인 버튼 → `/oauth2/authorization/kakao`로 **페이지 이동** → 돌아오면 `POST /api/auth/refresh`(`credentials: "include"`)로 access token → API 요청에 Bearer → 401이면 refresh 한 번 → 또 401이면 로그인 화면.

- 권한: 처음 로그인하면 `USER`. `ADMIN`은 DB에서 바꿔요 (다음 재발급부터, 최대 30분 안에 적용):
  `update account.users set role = 'ADMIN' where id = '<회원 ID>';`
- 주소 규칙: `/api/admin/**`은 ADMIN, `/api/users/**`는 로그인한 회원, 나머지는 누구나. 401·403도 Problem Details(`code`: `UNAUTHORIZED`·`FORBIDDEN`)로 와요.
- 다른 모듈 컨트롤러에서 로그인 회원: `@AuthenticationPrincipal LoginUser user` → `user.userId()` (`user.service.LoginUser`)
- 탈퇴는 hard delete예요. `users`를 지우면 소셜 계정·refresh token·탈퇴 티켓이 cascade로 같이 지워지고, `common/event/UserWithdrawn`으로 다른 모듈(알림 설정·푸시 구독 등)이 자기 데이터를 지워요. 재인증으로 받은 그 사용자의 제공자 토큰으로 **다시 로그인한 소셜만** 연결을 끊어요(카카오 unlink, 네이버 토큰 삭제, 구글 revoke). 제공자 토큰을 저장하지 않고 Admin 키도 두지 않아서, 함께 연결된 다른 소셜의 앱 동의는 사용자가 그 서비스에서 직접 해제해야 해요(탈퇴 시작 응답의 `otherProviders`). 연결 끊기가 실패해도 탈퇴는 완료돼요(로그만). 탈퇴 후 남은 access token(최대 30분)으로는 `/api/users/me`와 모든 쓰기 요청(GET·HEAD·OPTIONS 말고)이 401이에요 — 다른 모듈이 데이터를 지운 뒤 다시 만들지 못하게요. 만료된 refresh token과 끝내지 않은 탈퇴 티켓은 매일 04:30(한국 시각)에 지워요. 자세한 설계: 탈퇴·연결 끊기 문서.
- 모든 기기 로그아웃(권한 회수 등): `AuthTokenService.revokeAll(userId)`. 이미 발급한 access token은 남은 시간(최대 30분)까지 유효해요.
- 서버는 로그인 상태를 저장하지 않아요(STATELESS). 카카오 로그인 중간의 state 값만 잠깐 세션에 두고 로그인이 끝나면 지워요. CSRF는 꺼요 (Bearer 헤더 인증, 쿠키는 재발급·로그아웃에만 SameSite=Lax + POST).
- 소셜 계정에서는 닉네임만 받아요 (카카오 `profile_nickname`, 네이버 제공 정보 '별명', 구글 `profile`의 이름). 이메일·나이 등은 받지 않아요.
- 구글 scope에 `openid`를 넣지 않아요. 넣으면 OIDC 처리기로 가서 가입 처리(`SocialOAuth2UserService`)를 거치지 않아요.
- 같은 사람이어도 제공자가 다르면 다른 회원이에요 (이메일을 받지 않아 같은 사람인지 알 수 없어요). 계정 합치기는 로그인한 상태에서 다른 소셜 계정을 연결하는 기능으로 따로 만들어야 해요 (`social_accounts`는 한 회원에 여러 개를 붙일 수 있어요).
- 실패하면 `FRONTEND_URL/login?error=social&reason=<OAuth2 오류 코드>`로 돌아가고 서버 로그에 원인이 남아요 (`LoginFailureHandler`).
- 환경 변수: `KAKAO_CLIENT_ID`·`KAKAO_CLIENT_SECRET`, `NAVER_CLIENT_ID`·`NAVER_CLIENT_SECRET`, `GOOGLE_CLIENT_ID`·`GOOGLE_CLIENT_SECRET`, `FRONTEND_URL`, `OAUTH_REDIRECT_BASE_URL`(콜백 주소 `<값>/login/oauth2/code/{kakao,naver,google}`을 고정. 비우면 요청 주소 — 로컬, 운영은 프론트 주소), `JWT_SECRET`(32바이트 이상, 운영 필수) (`infra/.env.example`). 키가 없으면 그 제공자 로그인만 실패하고 서버는 떠요.
- 처음 최상위 관리자: 최상위는 화면에서 만들 수 없어요. 배포 뒤 관리자로 쓸 계정으로 가입하고, 그 회원 ID(`/api/users/me`의 `id`)를 `ADMIN_BOOTSTRAP_USER_ID`에 넣어 api를 다시 띄우면 최상위가 돼요 (`SuperAdminBootstrap`, 변경 기록에 남아요). 최상위가 이미 있으면 무시하고, 그 뒤로는 관리자 화면 「회원」의 넘기기로만 바꿔요. 처음 가입한 사람을 자동으로 올리지는 않아요.

## 웹 푸시 구독 (notification 모듈)

설계: `contracts/schemas/web-push.draft.md`. 기기(브라우저)마다 구독 한 줄이고, **구독이 있으면 그 기기 푸시가 켜진 거예요** (따로 켬·끔 설정 없음).

| 하는 일 | 요청 | 비고 |
| --- | --- | --- |
| VAPID 공개키 | `GET /api/v1/push/public-key` | 로그인 없이. `{publicKey}`. 설정이 없으면 503 `PUSH_NOT_CONFIGURED` |
| 이 기기 등록·갱신 | `PUT /api/users/me/push-subscriptions` | 본문은 `subscription.toJSON()` + `userAgent`. 204. 앱을 열 때마다 보내요 |
| 이 기기 해제 | `DELETE /api/users/me/push-subscriptions` | 본문 `{endpoint}`. 로그아웃 **전에**. 없어도 204 |
| 모든 기기 해제 | `DELETE /api/users/me/push-subscriptions?scope=all` | 본문 없이. 204 |
| 내 기기 목록 | `GET /api/users/me/push-subscriptions` | `[{id, userAgent, createdAt, updatedAt}]`, 최근에 쓴 기기부터. 주소·키는 주지 않아요 |
| 고른 기기 해제 | `DELETE /api/users/me/push-subscriptions/{id}` | 내 기기가 아니면 404 `PUSH_SUBSCRIPTION_NOT_FOUND` |

- 주소(`endpoint`)는 https이고 푸시 서비스 도메인(`fcm.googleapis.com`, `*.push.services.mozilla.com`, `*.push.apple.com`, `*.notify.windows.com`)이어야 해요. 알림 서버가 이 주소로 요청을 보내서, 아무 주소나 받으면 우리 서버가 남의 서버를 부르게 돼요
- 키는 base64url이고 길이를 확인해요 (`p256dh` 65바이트, `auth` 16바이트). 틀리면 400 `VALIDATION_FAILED` (오류 문구에 값은 넣지 않아요)
- 회원당 5대. 넘으면 마지막 등록(`updated_at`)이 가장 오래된 기기를 지워요. 다른 회원이 쓰던 주소를 등록하면 이 회원으로 옮겨요 (같은 브라우저에서 다른 계정으로 로그인)
- 주소·키는 로그에 남기지 않아요 (회원 ID와 푸시 서비스 도메인만). 탈퇴하면 `UserWithdrawn`으로 그 회원 기기를 모두 지워요
- 환경 변수: `PUSH_VAPID_PUBLIC_KEY` (`npx web-push generate-vapid-keys`로 만든 공개키). 개인키는 알림 서버에만 둬요

## 알림함 (notification 모듈)

알림 요청을 만들 때 받는 사람마다 한 줄 남겨요 (`notification.notifications`). 알림 설정(종류별 켬·끔)이나 기기·이메일이 없어도 남고, 설정은 푸시·이메일로 보낼지만 정해요. 같은 알림(dedupKey)은 한 번만, 90일 지나면 매일 04:40(한국 시각)에 지워요. 탈퇴하면 `UserWithdrawn`으로 모두 지워요.

| 하는 일 | 요청 | 비고 |
| --- | --- | --- |
| 내 알림 | `GET /api/users/me/notifications[?cursor=&size=&unread=true]` | 최근 것부터. `{items: [{id, type, target{type,id}, title, body, linkPath, createdAt, readAt}], nextCursor, hasNext}` |
| 안 읽은 수 | `GET /api/users/me/notifications/unread-count` | `{count}` |
| 읽음 | `POST /api/users/me/notifications/{id}/read` | 204. 이미 읽었어도 204, 내 알림이 아니면 404 `NOTIFICATION_NOT_FOUND` |
| 모두 읽음 | `POST /api/users/me/notifications/read-all` | 204 |

## 관심 공고·관심 조건·알림 설정 (user 모듈)

설계: `contracts/schemas/user-preferences.draft.md` 2장. 알림 대상자는 이 값으로 골라요 (`UserNotificationQueryService`, notification 모듈이 불러요).

| 하는 일 | 요청 | 비고 |
| --- | --- | --- |
| 관심 공고·정책 저장·지우기 | `PUT`·`DELETE /api/users/me/favorites/{notice\|benefit\|startup-support\|space-recruitment}/{id}` | 204. 없는 대상 404 `FAVORITE_TARGET_NOT_FOUND`, 200개 넘으면 409 `FAVORITE_LIMIT_EXCEEDED`. 합쳐진 공고는 남은 공고로 저장 |
| 내 관심 목록 | `GET /api/users/me/favorites[?targetType=&cursor=&size=]` | 최근 저장한 것부터 `{targetType, targetId, createdAt, title, organization, status, applyStart, applyEnd, linkPath}`. 대상이 사라졌으면 title·status가 null |
| 내 제보 | `GET /api/users/me/reports` | 공고·혜택·창업지원 사업·생활권·일반 제보를 합쳐 최근 100건 `{items: [{id, kind(NOTICE·BENEFIT·PROGRAM·AREA·GENERAL), targetId, targetTitle, field, reportedValue, note, status, result, reply, createdAt, handledAt, linkPath}]}` |
| 일반 제보 | `POST /api/v1/reports` (로그인) | 공고에 묶이지 않은 제보 `{field: MISSING_NOTICE·WRONG_INFO·APP_ERROR·ETC, note(필수), screen?, currentValue?}` → `{id, status}`. 관리자 제보 목록에 `GENERAL`, 같은 종류끼리 묶지 않아요. 답은 알림함에만(푸시·메일 없음) 남고 `/me?tab=reports`로 가요 |
| 관심 조건 | `GET`·`PUT`·`DELETE /api/users/me/interests/{housing\|business\|support}` | 지역은 시군구 5자리·시도 전체 xx000 (common.regions의 유효한 코드, 30개까지). `saved: false`면 저장 전이라 새 소식 알림을 받지 않아요 |
| 알림 설정 | `GET`·`PUT /api/users/me/notification-settings` | `{newNotice, newSupport, deadline, correction, followUp, quietEnabled}`. 저장 전에는 모두 켬·조용한 시간 끔. 끈 종류도 알림함에는 남아요 |

새 소식 대상자 지역 맞추기: 회원 지역과 공고·정책 지역이 같은 시도이고, 같은 시군구이거나 둘 중 하나가 시도 전체면 맞아요 (서울 전체를 고른 회원 ← 마포구 공고, 마포구 회원 ← 서울시 정책). 전국 대상은 "전국도 받기"를 켠 회원에게. 주거 공고는 공고 유형으로도 거르고(모르면 거르지 않음), 업종·창업 단계·지원 종류는 v1에서 저장만 해요. 지역을 모르는 정책은 새 소식으로 보내지 않아요.
