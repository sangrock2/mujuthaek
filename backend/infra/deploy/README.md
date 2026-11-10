# 배포 (EC2 · Docker Compose)

운영(prod EC2)과 개발(dev EC2) 서버는 같은 구성이에요. DB는 RDS, 원본 파일은 S3(EC2 IAM 역할), 프론트는 Vercel이 `/api/**`를 서버의 nginx(:80)로 넘겨요.

| 서버 | 서비스 | 배포 |
| --- | --- | --- |
| prod (3.37.131.73) | rabbitmq · nginx · api · notification · collector · extraction | 태그 `api-v1.2.0` 등 → `release.yml` |
| dev (52.79.106.144) | rabbitmq(shovel) · nginx · api · notification · extraction (수집기 없음) | `dev` 브랜치 push → `deploy-dev.yml` |

## 서버 폴더 `/opt/mujuthaek`
```
.env               GitHub Environment 비밀 ENV_FILE을 배포 때마다 그대로 써요 (chmod 600). 서버에서 고치지 않아요
versions.env       서비스별 이미지 태그 (API_TAG=v1.2.0 …). deploy.sh만 바꿔요
compose.prod.yml   compose.dev.yml   nginx/default.conf   rabbitmq/enabled_plugins   ← 이 폴더(infra/deploy)를 배포 때마다 복사
deploy.sh          shovel.sh          copy-prod-to-dev.sh
migrations/<서비스> deploy.sh가 그 버전 이미지에서 꺼낸 Flyway 파일 (collector·extraction)
```
손으로 볼 때: `docker compose -f compose.prod.yml --env-file .env --env-file versions.env ps` (logs, restart도 같은 방식)

## 첫 배포
1. GitHub → Actions → **Release** → Run workflow: 브랜치 `dev`(또는 `main`), 서비스 `all`, 버전 `v0.1.0`, **build 켬**
   - 네 서비스를 테스트·빌드해서 `ghcr.io/prgrms-be-devcourse/nbe11-13-final-team02/<서비스>:v0.1.0`으로 올리고 운영에 배포해요
   - 순서: rabbitmq → Flyway(collector·extraction) → api → notification → collector → extraction → nginx. api·notification은 각자 Flyway를 직접 돌려요
2. 개발 서버: Actions → **Deploy dev** → Run workflow(`dev`)로 세 서비스를 모두 빌드·배포해요. 그 뒤로는 `dev`에 올라온 바뀐 서비스만 배포돼요
3. 처음 최상위 관리자: 관리자로 쓸 계정으로 가입 → `/api/users/me`의 `id`를 ENV_FILE의 `ADMIN_BOOTSTRAP_USER_ID`에 넣고 api 다시 배포
4. 수집기는 처음 뜰 때 묶음마다 최신 N개만 골라 AI 추출로 보내요 (services/collector/README.md 「처음 수집 개수 제한」)

## 이후 배포 · 롤백
- 운영: `git tag api-v1.2.1 && git push origin api-v1.2.1` → 테스트 → 이미지 → 배포 → 릴리즈 노트
- 운영 (손으로): Actions › Release › Run workflow (브랜치 `main`, 서비스, 버전, **빌드 켬**) → 테스트 → 이미지 → 배포 → 태그 · 릴리즈 노트
  - 태그는 서비스 하나면 `api-v0.2.1`, 전체(all)면 `v0.2.1`. 배포한 main 커밋에 달고, 바뀐 PR 목록을 붙여요
  - **새 버전은 빌드를 켜요.** 빌드 끔은 이미 만든 버전으로 되돌릴 때만이에요 (없는 버전이면 이미지를 못 받아 배포가 실패하고 이전 버전으로 돌아가요). 되돌리기는 태그·노트를 남기지 않아요
- 롤백: Actions → Release → 서비스와 **이미 있는 버전**, build 끔. 또는 서버에서 `./deploy.sh prod api v1.2.0`
- deploy.sh는 헬스체크(api·notification `/actuator/health`, 파이썬은 Docker healthcheck, 최대 3분)가 실패하면 이전 태그로 되돌리고 실패로 끝나요.
  **DB 마이그레이션은 되돌리지 않아요** — 새 컬럼을 지우는 변경은 두 번에 나눠 올려요

## 개발 서버 데이터
개발 서버에는 수집기가 없고, 개발 추출은 `EXTRACTION_MODEL_MODE=recorded`라 새 공고의 결과를 만들지 못해요.
그래서 개발 서버는 **운영이 만든 결과**를 그대로 받아 운영과 같은 공고·혜택·생활권을 봐요. 두 단계예요 (둘 다 한 번만).

### 1. 지금까지의 데이터: copy-prod-to-dev.sh (운영 서버에서)
운영 api DB의 아래 테이블을 개발 api DB(`api_dev`)로 옮겨요. 개발 쪽 대상 테이블은 비우고 넣어요(한 트랜잭션, 실패하면 그대로).
```bash
cd /opt/mujuthaek
./copy-prod-to-dev.sh --dry-run      # 옮길 테이블·줄 수·같이 비워지는 개발 테이블만 보기
./copy-prod-to-dev.sh                # 개발 DB 계정·암호를 입력받아 복사 (--skip-big: 주소점·상가 빼기)
```
| 스키마 | 옮기는 테이블 | 옮기지 않음 |
| --- | --- | --- |
| notice | 공고·버전·원본 글·정정/후속·지역·추출 결과·생활권 점수·중복 후보·정책 판정 (전부) | `notice_reports`(회원 신고) |
| benefit | 혜택·조건·지원 내용 (전부) | — |
| area | 지역 경계·시설·상가(`stores`)·주소점(`address_points`)·도로명·업종 규칙·점수 규칙·생활권 지표·공고 위치·적재 기록 | `area_reports`(회원 제보) |
| eligibility | 기준값·기준 세트·대출 상품/규칙·규제지역·청약 예치금 | `criteria_set_history`(관리자 변경 기록) |
| account·notification·chat·traffic·common | — | 회원·알림·채팅·트래픽·아웃박스·처리 기록·Flyway 기록 |

- 스키마 단위로 골라요: 위 네 스키마에 테이블이 새로 생기면 같이 옮겨요 (제외 목록은 스크립트의 `EXCLUDE`)
- `stores`·`address_points`가 수 GB라 몇 분 걸려요. 주소 검색·상권이 필요 없으면 `--skip-big`
- 개발의 `notice_reports`처럼 옮기는 테이블을 참조하는 개발 테이블은 같이 비워져요 (`--dry-run`이 알려 줘요)
- 옮기는 테이블끼리의 외래키(공고 `merged_into` 같은 자기 참조 포함)는 넣는 동안 풀었다가 다시 걸어 검증해요. 개발 DB 계정이 테이블 주인이어야 해요
- 개발 api가 운영과 같은 버전(같은 마이그레이션)이어야 해요. 다르면 멈춰요
- pg_dump·psql은 `postgres:17-alpine` 이미지로 돌려요 (서버에 설치하지 않아요)

### 2. 이후 결과: shovel (운영 결과 이벤트를 개발로 복사)
운영 RabbitMQ의 `dev.mirror` 큐(3일·2만 건까지)가 `mujuthaek.events`의 결과 이벤트를 받아 두고, 개발 RabbitMQ의 shovel(from-prod)이 가져가요.
| 모드 | 복사하는 이벤트 | 쓰는 때 |
| --- | --- | --- |
| `results` (기본) | `extraction.completed`(공고·창업지원)·`policy.extracted`(혜택)·`area.source.ready`(생활권 원천) | 개발 api가 운영과 같은 데이터를 보게 |
| `raw` | `raw.notice.collected`·`raw.policy.collected`·`area.source.ready` | 개발 추출을 시험할 때 (recorded 모드라 결과가 안 나올 수 있어요) |
```bash
# 운영 서버: dev.mirror 큐·바인딩, 이 큐만 읽는 계정 shovel (암호는 입력)
./shovel.sh prod                     # results
./shovel.sh prod --mode raw          # raw로 바꾸기 (다른 모드 바인딩은 풀어요)
./shovel.sh prod --recreate          # 큐를 지우고 다시 만들기 (예전 raw 메시지가 쌓여 있을 때)
# 개발 서버: from-prod shovel (같은 암호 입력)
./shovel.sh dev
```
- 순서: `copy-prod-to-dev.sh` → `shovel.sh prod`(이미 raw로 만들었다면 `--recreate`) → `shovel.sh dev`. 복사와 shovel 사이에 운영에서 나온 결과는 3일 안이면 큐에 남아 있다가 들어가요
- 개발 api는 결과 이벤트를 받아 DB에만 써요. S3를 읽는 건 `area.source.ready`의 생활권 원천(`area/…`)뿐이고, 운영과 같은 버킷이라 개발 서버 IAM 역할에 그 버킷 읽기 권한이 있어야 해요. 공고·혜택 결과는 S3를 읽지 않아요(원문은 기관 링크)
- 상태: 개발 서버 관리 화면(`ssh -L 15672:127.0.0.1:15672 ubuntu@<dev>` → http://localhost:15672 → Admin → Shovel Status)

## 생활권·상권 원천 적재 (운영, 한 번만)
S3에 이미 올린 원천 파일을 목록으로 다시 적재 요청해요 (파일이 운영 버킷에 있어야 해요).
```bash
C="docker compose -f compose.prod.yml --env-file .env --env-file versions.env exec collector python -m mujuthaek_collector"
$C area-upload --skip-upload --manifest area/area_manifest.csv
$C area-upload --skip-upload --manifest area/area_manifest_boundary.csv
$C area-upload --skip-upload --manifest area/area_manifest_address.csv
```

### 적재 대기열 (area.load_runs)
api는 `area.source.ready`를 받으면 적재하지 않고 **기다림(PENDING) 기록만 남기고 바로 끝내요**. 적재는 api 안의 작업자가 하나씩 해요.
큰 파일(도로명주소 시도 하나에 100만 줄)이 RabbitMQ `consumer_timeout`(30분)을 넘겨 수신기가 멈추던 문제를 막으려고요.
- 상태: `PENDING`(기다림) → `RUNNING`(적재 중) → `SUCCEEDED` · `FAILED` · `SKIPPED`(같은 파일이 이미 성공)
- S3·DB 연결 오류는 1분·2분 뒤 다시 해요(파일당 3번). 적재 SQL은 90분이 넘으면 끊고 `FAILED`로 끝내요(`mujuthaek.area.load.statement-timeout`)
- api가 멈추거나 꺼져(자동 중지) 남은 `RUNNING`은 api가 뜰 때 `FAILED`로 닫고 다시 기다리게 넣어요. 슬랙으로도 알려요
- 실패한 파일을 다시 하려면 위 `area-upload --skip-upload`를 그 목록으로 다시 실행해요(같은 파일이어도 다시 기다리게 넣어요)
- 상태 보기 (api DB):
  ```sql
  select source, load_scope, status, attempts, started_at, finished_at, left(error, 80)
    from area.load_runs where started_at > now() - interval '2 days' order by started_at desc;
  ```

### 빠진 적재 다시 요청
`load_runs`에 줄이 없는 파일이 있으면(적재 요청이 큐에서 사라짐) 같은 목록으로 **다시 보내요**. 이미 적재한 파일은 api가 SKIPPED로 거르고,
기다리거나 도는 중인 파일은 넘어가서 두 번 적재하지 않아요.
```bash
C="docker compose -f compose.prod.yml --env-file .env --env-file versions.env exec collector python -m mujuthaek_collector"
$C area-upload --skip-upload --manifest area/area_manifest_address.csv --resend   # 도로명주소 (다른 목록도 같은 방법)
```
- `--resend`가 없으면 같은 파일은 이미 보낸 요청이라 다시 보내지 않아요(eventId가 원천·범위·지문으로 정해져요)
- 빠진 것 찾기 (api DB): 목록의 범위 중 `select distinct load_scope from area.load_runs where source = 'ADDRESS_ENTRANCE' and status in ('SUCCEEDED','PENDING','RUNNING')`에 없는 것

### RabbitMQ 데이터가 사라질 때 (호스트 이름)
RabbitMQ는 `rabbit@<호스트 이름>` 폴더에 큐·메시지·shovel 설정을 둬요. compose에서 `hostname: rabbitmq`로 고정해요.
고정하기 전에는 설정이 바뀐 배포로 컨테이너가 다시 만들어질 때마다 빈 폴더로 시작했어요 (2026-10-29 운영 배포에서 적재 요청 12건과 dev.mirror shovel이 사라짐).
- `hostname`을 처음 넣는 배포도 노드 이름이 바뀌어 **한 번 더 빈 상태로 시작해요.** 큐가 빈 때(적재·추출이 쉬는 때) 배포하고, 끝나면
  1. `./shovel.sh prod`(운영) · `./shovel.sh dev`(개발)로 dev.mirror shovel을 다시 만들고
  2. 빠진 적재가 있으면 위 「빠진 적재 다시 요청」
- 큐는 api·추출기가 뜰 때 다시 만들어요. 이전 폴더는 볼륨에 남아 있어요(`docker compose exec rabbitmq ls /var/lib/rabbitmq/mnesia`)

## 서비스 사이 연결
api가 같은 compose 안의 다른 서비스를 부르는 주소는 compose 파일에 있어요(`EXTRACTION_REVIEW_URL=http://extraction:8092`, 운영만 `COLLECTOR_ADMIN_URL=http://collector:8093`).
토큰은 ENV_FILE에 같은 값으로 넣어요. 양쪽이 같은 `.env`를 읽어요. `deploy.sh`가 빠진 키 이름을 경고해요(값은 출력하지 않아요)
| 키 | 쓰는 곳 | 없으면 |
| --- | --- | --- |
| `EXTRACTION_REVIEW_TOKEN` | api ↔ 추출기 검수 API | 다른 컨테이너 요청을 401로 거절 → 관리자 검수 화면 503 |
| `COLLECTOR_ADMIN_TOKEN` (운영) | api ↔ 수집기 관리자 API | 관리자 수집 현황 503. 개발 서버에는 수집기가 없어 늘 503이 정상 |
| `SLACK_WEBHOOK_URL` | api·수집기·추출기 운영 알림, 배포 알림 | 알림 없이 로그만 |

## 운영 알림 · 로그
- **슬랙**: `SLACK_WEBHOOK_URL`(추출기 비용 알림과 같은 웹훅, 채널은 웹훅에 묶여 있어요). 머리에 `[prod api]`처럼 환경(`MUJUTHAEK_ENV`)·서비스가 붙어요.
  같은 종류는 10분에 한 번만 보내고 그동안 생긴 횟수를 다음 알림에 붙여요
  - api: 처리하지 못한 오류(500), 다른 서비스 연결 실패 같은 503, 받은 메시지를 실패 큐로 보낼 때, area 적재 실패·멈춤 정리
  - 추출기: 공고·정책 메시지를 실패 큐로 보낼 때(이유 코드 포함), 월 AI 비용 80%
  - 수집기: 같은 출처가 3번 연달아 실패할 때, 목록이 계속 비어 사이트 구조 변경이 의심될 때
  - 배포: 개발 배포·운영 릴리즈 결과(성공·실패·되돌림), dev·main CI 실패. 웹훅은 GitHub 비밀 `SLACK_WEBHOOK_URL`, 없으면 그 환경의 ENV_FILE 안 값
- **로그**: 서버 디스크에만 있어요. 컨테이너마다 50MB × 6개까지 돌려써요(오래된 것부터 지워짐). 디스크 여유는 `df -h /`
  ```bash
  L="docker compose -f compose.prod.yml --env-file .env --env-file versions.env logs"
  $L --since 2h api | grep -E '"log.level":"(ERROR|WARN)"'   # api는 JSON(ECS) 한 줄씩
  $L --since 24h extraction | grep '\.dlq'                       # 실패 큐로 보낸 이유
  ```

## 실패 큐(DLQ) 보기 · 다시 처리
쌓인 메시지는 지우지 않고 볼 수 있어요(관리 API, `ack_requeue_true`는 다시 큐에 그대로 둬요). 운영 서버에서:
```bash
set -a; . ./.env; set +a
peek() {  # peek <큐> [개수]
  curl -s -u "$RABBITMQ_USER:$RABBITMQ_PASSWORD" -H 'content-type: application/json' \
    -X POST "http://127.0.0.1:15672/api/queues/%2F/$1/get" \
    -d "{\"count\":${2:-10},\"ackmode\":\"ack_requeue_true\",\"encoding\":\"auto\",\"truncate\":3000}" \
    | python3 -c 'import json,sys
for m in json.load(sys.stdin):
    h=m["properties"].get("headers") or {}; p=json.loads(m["payload"]).get("payload",{})
    print(h.get("x-error-reason","(이유 헤더 없음: 로그에서)"), h.get("x-failed-at",""), p.get("field"), p.get("rawPolicyId") or p.get("rawNoticeId"), p.get("version"))'
}
peek mujuthaek.raw.policy.dlq
```
- 이유 헤더(`x-error-reason`)는 이번 변경 뒤에 들어간 메시지부터 있어요: `AI_RETRY_EXHAUSTED:<코드>`(AI 일시 오류 5번 연속), `AI_FAILED:<코드>`(AI 영구 실패 + 규칙으로도 못 만듦), `ERROR:<예외>`(계약 검증·저장 등), `INVALID_EVENT`
- 그 전 메시지는 추출기 로그에서 찾아요(위 로그 명령, 로그가 돌려써져 지워졌으면 다시 처리해 보고 다시 실패하면 그때 이유가 남아요)
- 원인을 고친 뒤 원래 큐로 옮기기(이미 처리한 버전은 처리 기록으로 걸러져 AI를 다시 부르지 않아요):
  ```bash
  docker compose -f compose.prod.yml --env-file .env --env-file versions.env exec extraction \
    python -m mujuthaek_extraction replay-dlq --queue policy --limit 10    # 공고는 --queue notice
  ```
- api가 받는 큐의 실패(`mujuthaek.extraction.completed.dlq` 등)는 api 명령으로 옮겨요: `--notice.dead-letter.replay=N` (services/api README)

## 서버가 켜져 있는 시간
서버는 자동 중지·시작으로 09~18시(11/7부터 10~19시)에만 켜져 있어요. 하루 한 번 작업은 모두 11시대예요.
- api: 혜택 상태 11:00(+ 뜬 뒤 1분), 마감 D-3·D-1 알림 11:00 이후 첫 확인(그날 꺼져 있었으면 켜진 뒤 따라잡기), 정리 11:10~11:40
- notification: 정리 11:20·11:30
- collector: 정책 11:00, 정정 확인 11:30, 파일 정리 11:50, 처음 수집 고르기 12:30, 정책 다시 확인 금 13:00, 게시판 평일 9~19시 매시 5분

## 사람이 할 일
- 소셜 로그인 콘솔 3곳(카카오·네이버·구글)에 리다이렉트 URI 등록
  - `https://mujuthaek-fe.vercel.app/login/oauth2/code/kakao`, `…/naver`, `…/google`
  - dev 프론트 주소(Vercel Preview 고정 주소)의 같은 경로 `/login/oauth2/code/{kakao,naver,google}`
- Vercel rewrites: `/api/**`·`/oauth2/**`·`/login/oauth2/**` → `http://<탄력적 IP>:80` (프론트 저장소 작업, 환경 변수 `API_ORIGIN`)
- ENV_FILE: `FRONTEND_URL`(로그인 뒤 돌아갈 프론트 주소), `OAUTH_REDIRECT_BASE_URL`(소셜 로그인 콜백 주소의 앞부분), `CORS_ORIGINS`에 dev 프론트 주소
  - 운영: `FRONTEND_URL=https://mujuthaek-fe.vercel.app`, `OAUTH_REDIRECT_BASE_URL=https://mujuthaek-fe.vercel.app`
  - 개발: 두 값 모두 dev 프론트 주소 (Vercel Preview 고정 주소)
  - `OAUTH_REDIRECT_BASE_URL`이 없으면 콜백 주소를 요청 주소로 만들어요. Vercel → nginx → api를 거치면 http·서버 IP가 될 수 있어서 Google이 거절해요
- 브라우저는 Vercel 주소만 불러요. api는 nginx가 넘긴 X-Forwarded-Host·Proto로 OAuth redirect-uri를 `https://<Vercel 주소>` 기준으로 만들고,
  refresh 토큰 쿠키(`Path=/api/auth; Secure; HttpOnly; SameSite=Lax`, Domain 없음)도 Vercel 주소에 저장돼요

## 주의
- `.env` 값에 `$`가 있으면 compose가 변수로 읽어요. 암호에 `$`를 쓰지 않거나 `$$`로 써요
- 파이썬 워커의 RabbitMQ 주소는 `amqp://RABBITMQ_USER:RABBITMQ_PASSWORD@rabbitmq:5672/`로 만들어요. 암호에 `@ : / ? #`가 있으면 안 돼요
- Flyway 계정은 기본 `collector_app`·`extraction_app`이에요. 다르면 ENV_FILE에 `COLLECTOR_DB_USER`·`EXTRACTION_DB_USER`를 넣어요
- 관리 화면(15672)·api(8080)·notification(8081)은 서버 안(127.0.0.1)에서만 열려요. 밖에서는 nginx(:80)만

## 문제 해결
| 로그 | 원인 · 할 일 |
| --- | --- |
| scp·ssh 단계 `dial tcp …:22: i/o timeout` | 서버가 꺼진 시간이에요(자동 중지). 켜진 뒤 그 실행을 Re-run 하거나 Run workflow |
| Flyway `password authentication failed for user "…_app"` | Flyway 계정·암호가 DB와 달라요. ENV_FILE의 `EXTRACTION_DB_USER`·`COLLECTOR_DB_USER`(기본 `extraction_app`·`collector_app`)와 `…_DB_PASSWORD`를 `…_DB_URL` 안의 값과 같게. deploy.sh는 그 서비스만 이전 태그로 되돌려요 |
| 헬스체크 3분 초과 → 「이전 태그로 되돌려요」 | `docker compose -f compose.<env>.yml --env-file .env --env-file versions.env logs --tail 200 <서비스>`로 원인 확인 |
| RabbitMQ 관리 화면에서 `mujuthaek.area.source-ready` consumers 0, 메시지가 쌓임 | 이전 버전 api가 큰 적재를 받는 자리에서 하다가 30분 `consumer_timeout`에 채널이 닫힌 거예요. 지금 버전은 대기열로 떼어 생기지 않아요. 생기면 api 재시작(남은 RUNNING은 뜰 때 정리돼요) |
| api 로그 「검수 API에 연결하지 못했어요」 | api가 추출기 주소를 모름(compose의 `EXTRACTION_REVIEW_URL`) 또는 추출기가 꺼짐. 「…오류로 답했어요 (status 401)」이면 `EXTRACTION_REVIEW_TOKEN`이 한쪽에 없음 |
| api 로그 「수집기 관리자 API에 연결하지 못했어요」·수집 현황 503 | 운영: 위와 같이 `COLLECTOR_ADMIN_URL`·`COLLECTOR_ADMIN_TOKEN` 확인. 개발: 수집기가 없어 정상 |
| 예전 실행을 Re-run 했더니 서비스가 옛 버전으로 | Re-run은 그 실행의 커밋(`dev-<7자리>`)으로 배포해요. 최신으로 맞추려면 Run workflow(세 서비스 전부) |
