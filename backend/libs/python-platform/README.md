# mujuthaek-platform

파이썬 워커(collector·extraction)가 같이 쓰는 기술 코드예요. 업무 규칙은 넣지 않아요.

| 모듈 | 함수 | 하는 일 |
| --- | --- | --- |
| `ids` | `uuid7()` | 시간 순으로 정렬되는 UUID v7 (DB 기본 키) |
| `events` | `new_event(type, producer, payload)` | 이벤트 봉투 만들기 (`eventId`, `eventType`, `schemaVersion`, `occurredAt`, `producer`, `payload`) |
| `outbox` | `add(cur, event)` | 저장과 **같은 트랜잭션**에서 아웃박스 테이블에 이벤트 기록 |
|  | `open_channel(connection)` | 발행용 채널 열기. 확인(confirm) 모드를 켜고 exchange `mujuthaek.events`(topic)를 만들어 둠 |
|  | `relay_once(conn, channel)` | 안 보낸 이벤트를 발행. 라우팅 키는 `eventType`. 브로커가 거부하거나 받을 큐가 없으면 예외가 나고 아웃박스에 남음 |
| `broker` | `connect(url)` | RabbitMQ 연결 (pika) |
| `db` | `connect(url)` | PostgreSQL 연결 (psycopg 3) |
| `logging` | `setup(service)` | JSON 한 줄 로그. `extra` 값도 칸으로 남김 |
| `contracts` | `validate_event(event)` | `contracts/events/<eventType>.v<schemaVersion>.json`으로 검사 (테스트용, jsonschema 필요) |
| `slack` | `SlackNotifier.from_env(name, env_file)` · `send(text)` | 슬랙 수신 웹훅으로 글 하나 보내기. 주소는 환경 변수 → `env_file` 순서로 읽고, 없으면 보내지 않고 경고 로그 한 번. 실패는 `SlackError`, 주소는 로그·예외에 안 남김 |
| `slack` | `QuietAlerts.from_env(service)` · `send(kind, title, detail)` | 운영 오류 알림. 같은 종류는 10분에 한 번(그동안 횟수는 다음 알림에), 머리 `[MUJUTHAEK_ENV 서비스]`, 실패해도 예외 없이 경고 로그 |

## 쓰는 법
워커의 `pyproject.toml`에 경로로 연결해요.

```toml
dependencies = ["mujuthaek-platform"]

[tool.uv.sources]
mujuthaek-platform = { path = "../../libs/python-platform", editable = true }
```

```python
from mujuthaek_platform import broker, outbox
from mujuthaek_platform.events import new_event

event = new_event("raw.notice.collected", "collector", payload)
with conn.transaction(), conn.cursor() as cur:
    cur.execute("insert into …")  # 업무 데이터 저장
    outbox.add(cur, event)  # 같은 트랜잭션

channel = outbox.open_channel(broker.connect(url))  # 연결할 때 한 번
outbox.relay_once(conn, channel)  # 발행기 (5초마다)
```

```python
from mujuthaek_platform.slack import SlackError, SlackNotifier

# 서비스 전용 이름을 먼저 쓰려면 ("COLLECTOR_SLACK_WEBHOOK_URL", "SLACK_WEBHOOK_URL")
notifier = SlackNotifier.from_env("SLACK_WEBHOOK_URL")
try:
    notifier.send("[collector] 수집 실패가 이어져요")
except SlackError:
    log.warning("슬랙 알림 실패")  # 알림 실패가 본 작업을 막지 않게
```

## 아웃박스 테이블
각 워커의 마이그레이션에 이 모양으로 만들어요. `payload`에는 **봉투 전체**가 들어가요. 받는 쪽이 `eventId`로 중복을 걸러야 해서예요.

```sql
create table outbox (
    event_id       uuid primary key,
    event_type     text not null,
    schema_version int  not null,
    payload        jsonb not null,
    created_at     timestamptz not null default now(),
    published_at   timestamptz,
    attempts       int  not null default 0
);
```

발행은 "최소 한 번"이에요. 보낸 직후 DB를 갱신하기 전에 죽으면 같은 이벤트를 다시 보내요. 그래서 받는 쪽은 `processed_events`로 `eventId`를 한 번만 처리해요.

## 개발
```bash
cd libs/python-platform
uv run ruff check && uv run ruff format --check && uv run pytest
```
