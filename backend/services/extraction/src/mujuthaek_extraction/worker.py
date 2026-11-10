"""extraction 워커: 큐 소비 → 처리 → 저장·아웃박스, 아웃박스 발행기(2초), 검수 API(:8092).

큐 (팀 이벤트 흐름 문서)
  교환기 mujuthaek.events(topic) ── raw.notice.collected ──▶ 큐 mujuthaek.raw.collected (extraction이 선언)
  처리 실패·형식 오류 메시지는 재시도 없이 mujuthaek.dlx → mujuthaek.raw.collected.dlq
  교환기 mujuthaek.events ── raw.policy.collected ──▶ 큐 mujuthaek.raw.policy: 창업지원·사업공간 모집이면 판정 틀을 만들어
  extraction.completed(judgment)를 아웃박스에 넣습니다. 정책 이벤트는 수집기가 발행만 하고 이 큐를 꺼내는 곳은 extraction뿐입니다
  (2026-10-23 팀 확인). 실패는 mujuthaek.raw.policy.dlq로 직접 옮기고 ack합니다(이미 만들어진 큐라 dead-letter 인자를 붙이지 않음)
  (AI 영구 실패로 틀을 못 만들었거나 AI 일시 실패가 MAX_AI_RETRIES번 이어진 메시지도 .dlq로)
  prefetch 1: 한 번에 한 건만 처리합니다(AI 호출이 길어서). 처리는 별도 스레드에서 하고 ack는 연결 스레드로 넘깁니다(pika 하트비트 유지).
  DB 연결은 메시지마다 새로 엽니다. 예전에는 하나를 계속 써서 DB가 한 번 끊기면 이후 메시지가 전부 .dlq로 갔습니다(검토 2026-10-16).
  DB를 못 쓰면 .dlq가 아니라 잠시 뒤 큐로 되돌립니다(자료 문제가 아니라 일시 장애이므로).
  큐 연결이 끊겨 같은 메시지가 다시 오면, 같은 이벤트를 처리 중인 스레드가 끝나기를 기다렸다가 이미 끝났는지 다시 봅니다(AI 비용 두 번 방지).
  다시 처리할 때는 성공했던 모델 호출을 DB(extraction_call_cache)에서 다시 쓰고, 예산은 앞선 처리가 쓴 비용부터 셉니다(model/call_cache.py).
  같은 원본 버전은 한 번에 한 처리만 합니다(DB 처리권 extraction_claims). 다른 처리가 잡고 있으면 잠시 뒤 큐로 되돌립니다.
"""

from __future__ import annotations

import functools
import json
import logging
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

from psycopg_pool import ConnectionPool

from mujuthaek_extraction.assemble.regions import RegionCodeTable
from mujuthaek_extraction.benefit.build import build_payload
from mujuthaek_extraction.benefit.codes import rules_for
from mujuthaek_extraction.benefit.reading import read_benefit
from mujuthaek_extraction.config import Settings
from mujuthaek_extraction.contracts import tools
from mujuthaek_extraction.cost_alert import CostAlert
from mujuthaek_extraction.health import Health
from mujuthaek_extraction.intake import LocalDirSourceReader
from mujuthaek_extraction.model import ModelError
from mujuthaek_extraction.model.call_cache import PostgresCallCache
from mujuthaek_extraction.model.factory import ModelFactory
from mujuthaek_extraction.model.fallback import FallbackOnErrorModel
from mujuthaek_extraction.model.spend import SpendLedger
from mujuthaek_extraction.pipeline import EVENT_TYPE, PRODUCER, Outcome, process
from mujuthaek_extraction.publish import POLICY_FIELDS, not_sent_reason, policy_completed_payload, policy_frame_detail
from mujuthaek_extraction.review_api import ReviewService, serve
from mujuthaek_extraction.rules.policy.reading import read_policy
from mujuthaek_extraction.s3_reader import S3SourceReader
from mujuthaek_extraction.store import DuplicateEvent, JobStore
from mujuthaek_extraction.usage import log_fields
from mujuthaek_platform import broker, db, outbox
from mujuthaek_platform.events import new_event
from mujuthaek_platform.slack import QuietAlerts, SlackNotifier

log = logging.getLogger(__name__)
EXCHANGE = outbox.EXCHANGE
DLX = "mujuthaek.dlx"
QUEUE = "mujuthaek.raw.collected"
DLQ = QUEUE + ".dlq"
ROUTING_KEY = "raw.notice.collected"
# 정책 원본(raw.policy.collected). 이 큐를 꺼내 판정 틀을 만듭니다(받을 큐가 없으면 collector 발행기(mandatory)가 거절당해 같은 묶음의
# 공고 이벤트까지 막히므로 선언도 유지). 큐는 dev에서 인자 없이 먼저 만들어져 있어, 인자를 바꾸면 다시 선언할 때 거절당합니다(PRECONDITION_FAILED).
# 그래서 실패 메시지는 dead-letter 대신 POLICY_DLQ로 직접 옮깁니다(finish_policy)
POLICY_QUEUE = "mujuthaek.raw.policy"
POLICY_DLQ = POLICY_QUEUE + ".dlq"
POLICY_ROUTING_KEY = "raw.policy.collected"
COMPLETED_SCHEMA = "events/extraction.completed.v1.json"
# 주거·이주 혜택 정제 결과 (담당자3 초안 policy-extracted.draft.md, 2026-10-25). 받는 쪽은 api benefit
BENEFIT_EVENT_TYPE = "policy.extracted"
BENEFIT_SCHEMA = "events/policy.extracted.v1.json"
BENEFIT_FIELDS = frozenset({"BENEFIT"})
# 혜택 정제 결과를 보관할 큐(2026-10-25 로컬 실제 흐름 시험에서 발견): 받는 쪽(api benefit)이 아직 큐를 만들지 않아 아웃박스 발행기(mandatory)가
# 「받을 곳 없음」으로 거절당하고, 그 뒤의 공고 결과 이벤트까지 막혔습니다. raw.policy와 같은 까닭으로 보내는 쪽이 인자 없이 선언해 둡니다
# (받는 쪽이 같은 이름을 다른 인자로 선언하면 PRECONDITION_FAILED이니 인자 없이 쓰거나 이 선언을 함께 바꿔야 함)
BENEFIT_QUEUE = "mujuthaek.policy.extracted"
CLAIM_LEASE_SECONDS = 300  # 처리권 기한. 워커가 죽으면 이 시간 뒤 다른 처리가 이어받습니다
CLAIM_RENEW_SECONDS = 60  # 처리 중 기한을 늘리는 간격(공고 하나가 30분 넘게 걸린 실측이 있어 기한을 계속 늘림)
CLAIM_BUSY_SECONDS = 30  # 다른 처리가 잡고 있을 때 큐로 되돌리기 전 기다림
DB_RETRY_SECONDS = 30  # DB 장애 때 큐로 되돌리기 전 기다림(바로 되돌리면 같은 메시지가 쉬지 않고 돎)
BUDGET_WAIT_SECONDS = 600  # 하루·월 전체 비용 상한에 닿았을 때 큐로 되돌리기 전 기다림
MAX_INTERRUPTED_RUNS = 3  # 같은 이벤트가 저장 전에 이만큼 중단되면 더 처리하지 않습니다(같은 충돌이 끝없이 반복되지 않게)


def _db_errors() -> tuple[type[BaseException], ...]:
    import psycopg

    return (psycopg.OperationalError, psycopg.InterfaceError)


def declare(channel) -> None:
    channel.exchange_declare(exchange=EXCHANGE, exchange_type="topic", durable=True)
    channel.exchange_declare(exchange=DLX, exchange_type="topic", durable=True)
    channel.queue_declare(queue=DLQ, durable=True)
    channel.queue_bind(queue=DLQ, exchange=DLX, routing_key=ROUTING_KEY)
    channel.queue_declare(queue=QUEUE, durable=True, arguments={"x-dead-letter-exchange": DLX})
    channel.queue_bind(queue=QUEUE, exchange=EXCHANGE, routing_key=ROUTING_KEY)
    channel.queue_declare(queue=POLICY_QUEUE, durable=True)
    channel.queue_bind(queue=POLICY_QUEUE, exchange=EXCHANGE, routing_key=POLICY_ROUTING_KEY)
    channel.queue_declare(queue=POLICY_DLQ, durable=True)
    # api가 받을 큐라 api의 RabbitTopology.queue와 같은 모양(실패 큐 x-dead-letter-exchange + 이름.dlq)으로 선언해요.
    # 인자가 다르면 나중에 api가 같은 큐를 선언할 때 PRECONDITION_FAILED가 나요(2026-10-25 검토)
    channel.queue_declare(queue=BENEFIT_QUEUE + ".dlq", durable=True)
    channel.queue_bind(queue=BENEFIT_QUEUE + ".dlq", exchange=DLX, routing_key=BENEFIT_EVENT_TYPE)
    channel.queue_declare(queue=BENEFIT_QUEUE, durable=True, arguments={"x-dead-letter-exchange": DLX})
    channel.queue_bind(queue=BENEFIT_QUEUE, exchange=EXCHANGE, routing_key=BENEFIT_EVENT_TYPE)


DLQ_TARGETS = {"notice": (DLQ, QUEUE), "policy": (POLICY_DLQ, POLICY_QUEUE)}


def replay_dlq(channel, dlq: str, queue: str, limit: int) -> int:
    """.dlq 메시지를 원래 큐로 최대 limit건 되돌립니다(원인을 고친 뒤 운영자가 실행). 옮긴 뒤에만 .dlq에서 지웁니다.
    같은 정책·공고 버전은 처리 기록으로 걸러지므로, 이미 끝난 것이 섞여 있어도 AI를 다시 부르지 않습니다."""
    moved = 0
    while moved < limit:
        method, properties, body = channel.basic_get(queue=dlq, auto_ack=False)
        if method is None:
            break
        channel.basic_publish(exchange="", routing_key=queue, body=body, properties=properties)
        channel.basic_ack(method.delivery_tag)
        moved += 1
    return moved


def finish_policy(channel, delivery_tag: int, decision: str, body: bytes, properties: Any = None, reason: str | None = None) -> None:
    """정책 메시지의 결정을 큐에 알립니다. .dlq면 본문을 POLICY_DLQ로 옮긴 뒤 ack합니다(정책 큐에는 dead-letter 인자가 없어
    reject하면 메시지가 사라짐). 옮기기가 실패하면 예외가 나서 ack하지 않으므로 연결이 끊긴 뒤 메시지가 다시 옵니다.
    .dlq로 옮길 때 실패 이유를 헤더(x-error-reason·x-failed-at)에 남겨, 쌓인 메시지만 봐도 왜 실패했는지 알 수 있게 합니다."""
    if decision == "ack":
        channel.basic_ack(delivery_tag)
    elif decision == "requeue":
        channel.basic_nack(delivery_tag, requeue=True)
    else:
        channel.basic_publish(exchange="", routing_key=POLICY_DLQ, body=body, properties=failure_properties(properties, reason))
        channel.basic_ack(delivery_tag)


def failure_properties(properties: Any, reason: str | None) -> Any:
    """원래 속성에 실패 이유 헤더를 더한 복사본(원래 헤더는 그대로 둡니다)."""
    import pika

    base = properties if properties is not None else pika.BasicProperties()
    headers = dict(getattr(base, "headers", None) or {})
    headers["x-error-reason"] = (reason or "UNKNOWN")[:300]
    headers["x-failed-at"] = datetime.now(UTC).isoformat(timespec="seconds")
    return pika.BasicProperties(
        content_type=base.content_type,
        content_encoding=base.content_encoding,
        delivery_mode=base.delivery_mode or 2,
        message_id=base.message_id,
        timestamp=base.timestamp,
        type=base.type,
        app_id=base.app_id,
        correlation_id=base.correlation_id,
        headers=headers,
    )


def _note(why: list[str] | None, reason: str) -> None:
    if why is not None:
        why.append(reason)


class BudgetExhausted(Exception):
    """하루·월 전체 비용 상한에 닿아 새 처리를 시작하지 않습니다. 메시지는 잠시 뒤 큐로 되돌리고, 다시 처리는 다음 차례로 미룹니다."""


class AiUnavailable(Exception):
    """AI 호출이 일시적으로 실패했습니다(한도 초과·시간 초과 등). 정책 메시지를 잠시 뒤 큐로 되돌립니다.
    구간 칸 규칙으로 대신 만들면 그 버전의 AI 틀은 다시 만들어지지 않습니다(리뷰 2026-10-22)."""


class AiFailed(Exception):
    """AI 읽기가 영구 오류로 실패했고 구간 칸 규칙으로도 틀을 만들지 못했습니다. 기록 없이 ack하지 않고 .dlq로 보냅니다(리뷰 2026-10-22)."""


# 정책 판정에서만 일시 실패로 보는 코드: 로컬 AI 연결 실패(주거 추출은 대체 모델로 넘기려 영구 오류로 둠, model/local_ai.py)
POLICY_RETRY_CODES = {"CONNECTION", "SKIPPED_DOWN"}
MAX_AI_RETRIES = 5  # 같은 정책 메시지가 AI 일시 실패로 이만큼 연속 되돌아오면 .dlq로(5xx가 계속되면 끝없이 돌지 않게)


class RetryCounter:
    """같은 정책 원본 버전의 연속 AI 일시 실패 횟수(워커 프로세스 안에서만 셉니다. 다시 시작하면 처음부터)."""

    def __init__(self, limit: int = MAX_AI_RETRIES):
        self.limit = limit
        self._counts: dict[str, int] = {}
        self._lock = threading.Lock()

    def fail(self, key: str) -> bool:
        """실패 한 번을 세고, limit번째면 기록을 지우고 True(.dlq로 보낼 차례)."""
        with self._lock:
            count = self._counts.get(key, 0) + 1
            if count >= self.limit:
                self._counts.pop(key, None)
                return True
            self._counts[key] = count
            return False

    def clear(self, key: str) -> None:
        with self._lock:
            self._counts.pop(key, None)


def _policy_retry_key(raw_event: dict[str, Any]) -> str:
    """연속 실패를 셀 열쇠: 정책 ID·버전(재발행돼 eventId가 달라도 같은 원본), 없으면 eventId."""
    payload = raw_event.get("payload") if isinstance(raw_event.get("payload"), dict) else {}
    policy, version = _uuid_or_none(payload.get("rawPolicyId")), payload.get("version")
    if policy and isinstance(version, int) and not isinstance(version, bool):
        return f"{policy}:{version}"
    return f"event:{raw_event.get('eventId')}"


class ClaimBusy(Exception):
    """같은 원본 버전을 다른 처리가 하고 있습니다. 메시지를 잠시 뒤 큐로 되돌립니다(검토 2026-10-20: 동시 처리로 예산을 몇 배 씀)."""


def _uuid_or_none(value: Any) -> str | None:
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, TypeError):
        return None


def _claim_key(raw_event: dict[str, Any]) -> tuple[str, int] | None:
    payload = raw_event.get("payload") if isinstance(raw_event.get("payload"), dict) else {}
    raw_post_id, raw_version = payload.get("rawPostId"), payload.get("version")
    try:
        raw_post_id = str(uuid.UUID(str(raw_post_id)))
    except ValueError:
        return None
    return (raw_post_id, raw_version) if isinstance(raw_version, int) and not isinstance(raw_version, bool) else None


@contextmanager
def claimed(store: JobStore, raw_event: dict[str, Any]):
    """원본 버전 처리권을 잡고 처리 동안 기한을 늘립니다. 원본 ID·버전이 없으면(형식 오류) 잡지 않습니다."""
    key = _claim_key(raw_event)
    if key is None:
        yield
        return
    owner = uuid.uuid4().hex
    if not store.claim(*key, owner, CLAIM_LEASE_SECONDS):
        raise ClaimBusy(f"{key[0]} v{key[1]}")
    stop = threading.Event()

    def renew() -> None:
        while not stop.wait(CLAIM_RENEW_SECONDS):
            try:
                if not store.renew_claim(*key, owner, CLAIM_LEASE_SECONDS):
                    log.warning("처리권을 잃었습니다(기한이 지나 다른 처리가 잡음)", extra={"rawPostId": key[0], "rawVersion": key[1]})
                    return
            except Exception:
                log.exception("처리권 기한을 늘리지 못했습니다")

    keeper = threading.Thread(target=renew, daemon=True)
    keeper.start()
    try:
        yield
    finally:
        stop.set()
        keeper.join(timeout=5)
        try:
            store.release_claim(*key, owner)
        except Exception:
            log.exception("처리권을 풀지 못했습니다(기한이 지나면 풀림)")


class Processor:
    """메시지 본문 1건 처리. 큐 없이도(파일·다시 처리) 같은 경로를 씁니다."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.models = ModelFactory(settings)
        if settings.local_files_dir:  # S3 키가 정해지기 전 시험용 PDF 폴더
            self.reader = LocalDirSourceReader(settings.local_files_dir)
        else:
            self.reader = S3SourceReader(settings.s3_bucket, settings.s3_endpoint, settings.s3_access_key, settings.s3_secret_key)
        self.regions = RegionCodeTable.from_csv(settings.region_table, settings.region_table_date)
        self._running: dict[str, threading.Event] = {}  # 처리 중인 eventId → 끝나면 켜짐
        self.cost_alert = CostAlert.from_url(settings.monthly_budget_usd, settings.slack_webhook_url)  # 월 상한 80% 슬랙 경고
        self._running_lock = threading.Lock()

    def run(self, raw_event: dict[str, Any], store: JobStore | None = None, ledger: SpendLedger | None = None) -> Outcome:
        """store가 있으면 그 연결로 호출 캐시를 쓰고, 같은 원본 버전의 앞선 처리 비용부터 예산을 셉니다(DB 오류는 위로 올려 큐로 되돌림).
        ledger가 있으면 호출마다 DB 비용 장부에 적고 하루·월 전체 상한을 지킵니다. 처리 중 전체 상한에 걸리면 결과를 발행하지 않고
        다시 처리 대상(FAILED)으로 남깁니다(빠진 섹션이 있는 결과를 내보내지 않게)."""
        cache, spent = (PostgresCallCache(store.conn), store.spent_before(raw_event)) if store is not None else (None, 0.0)
        models = self.models.for_notice(cache=cache, spent_before_usd=spent, ledger=ledger)
        outcome = self._process(raw_event, models)
        refusal = models.budget.refusal if models.budget else None
        if refusal:
            log.warning("전체 비용 상한에 걸려 결과를 발행하지 않고 다시 처리로 미룹니다", extra={"reason": refusal})
            return Outcome("FAILED", cost_usd=outcome.cost_usd, error=f"전체 비용 상한: {refusal}", attempts=outcome.attempts, usage=outcome.usage)
        return outcome

    def _process(self, raw_event: dict[str, Any], models) -> Outcome:
        try:
            return process(
                raw_event,
                models=models,
                reader=self.reader,
                regions=self.regions,
                clock=lambda: datetime.now(UTC),
                new_event=new_event,
                require_pdf=self.settings.require_pdf,
                method=self.settings.extraction_method,
                parallel_calls=self.settings.parallel_calls,
                parallel_stagger=self.settings.parallel_stagger_seconds,
            )
        except Exception as error:  # 예상 못 한 결함도 작업 기록에 남기고 다시 처리할 수 있게 둡니다
            log.exception("처리 중 오류")
            # 이미 쓴 비용을 남겨야 다음 처리가 원본 버전 누적 예산(spent_before)에서 빼고 셉니다(검토 2026-10-20: 예외면 $0으로 기록됨)
            spent = models.budget.charged_usd() if models.budget else 0.0
            return Outcome("FAILED", cost_usd=spent, error=f"처리 중 오류: {type(error).__name__}: {str(error)[:300]}")

    def handle(self, store: JobStore, raw_event: dict[str, Any]) -> str | None:
        """처리하고 저장합니다. 이미 끝난 이벤트면 None."""
        event_id = raw_event.get("eventId")
        if not isinstance(event_id, str):
            with claimed(store, raw_event):
                return self._handle(store, raw_event, event_id)
        while True:
            with self._running_lock:
                other = self._running.get(event_id)
                if other is None:
                    mine = self._running[event_id] = threading.Event()
                    break
            other.wait()  # 같은 이벤트를 다른 스레드가 처리 중: 끝난 뒤 다시 확인합니다
        try:
            with claimed(store, raw_event):
                return self._handle(store, raw_event, event_id)
        finally:
            with self._running_lock:
                self._running.pop(event_id, None)
            mine.set()

    def open_ledger(self, raw_event: dict[str, Any]) -> SpendLedger | None:
        """DB 비용 장부(전용 연결). DB 설정이 없거나 유료 API를 쓰지 않으면 None."""
        if not self.settings.db_url or self.settings.model_mode != "auto":
            return None
        key = _claim_key(raw_event)
        payload = raw_event.get("payload") if isinstance(raw_event.get("payload"), dict) else {}
        if key is None:  # 정책 수집 이벤트는 rawPolicyId: 비용 장부의 원본 칸에 정책 ID를 적어 정책별 비용을 볼 수 있게(리뷰 2026-10-22)
            policy, version = _uuid_or_none(payload.get("rawPolicyId")), payload.get("version")
            key = (policy, version) if policy and isinstance(version, int) else None
        scope = {
            "eventId": _uuid_or_none(raw_event.get("eventId")),
            "rawPostId": key[0] if key else None,
            "rawVersion": key[1] if key else None,
            "field": payload.get("field") if isinstance(payload.get("field"), str) else None,  # 분야별 비용 집계(cost_alert.py)
        }
        return SpendLedger(
            db.connect(self.settings.db_url),
            daily_usd=self.settings.daily_budget_usd,
            monthly_usd=self.settings.monthly_budget_usd,
            scope=scope,
            alert=self.cost_alert,
        )

    def _handle(self, store: JobStore, raw_event: dict[str, Any], event_id: Any) -> str | None:
        if isinstance(event_id, str) and store.already_processed(event_id):
            log.info("이미 처리한 이벤트", extra={"eventId": event_id})
            return None
        valid_id = _uuid_or_none(event_id)
        key = _claim_key(raw_event)
        payload = raw_event.get("payload") if isinstance(raw_event.get("payload"), dict) else {}
        if valid_id and key and not payload.get("reprocess") and store.version_published(*key):
            # 같은 원본 버전을 다른 eventId로 다시 받음(수집기 재발행): 이미 발행했으므로 AI를 다시 부르지 않습니다(2026-10-21)
            store.mark_processed(valid_id, str(raw_event.get("eventType") or "unknown"))
            log.info("이미 발행한 원본 버전이라 처리하지 않았습니다", extra={"eventId": event_id, "rawPostId": key[0], "rawVersion": key[1]})
            return None
        if valid_id:
            interrupted = store.interrupted_runs(valid_id)
            if interrupted >= MAX_INTERRUPTED_RUNS:
                error = f"결과를 저장하기 전에 {interrupted}번 중단되어 더 처리하지 않습니다(메모리·PDF 처리 확인 필요)."
                log.error("처리 중단이 반복되어 멈춥니다", extra={"eventId": event_id, "interrupted": interrupted})
                return store.save(raw_event, Outcome("INTERRUPTED", error=error))
        ledger = self.open_ledger(raw_event)
        try:
            if ledger is not None and (reason := ledger.room(self.settings.notice_budget_usd)):
                raise BudgetExhausted(reason)
            if valid_id:
                store.record_start(valid_id)
            outcome = self.run(raw_event, store, ledger)
        finally:
            if ledger is not None:
                ledger.close()
        try:
            job_id = store.save(raw_event, outcome, ledger.run_id if ledger is not None else None)
        except DuplicateEvent:
            log.info("같은 이벤트를 다른 처리가 먼저 끝내 저장하지 않았습니다", extra={"eventId": event_id})
            return None
        # 작업마다 한 줄: 상태·비용과 측정 합계(시간·토큰·호출 수). 원문·오류 문구·키는 넣지 않습니다
        log.info(
            "작업 저장",
            extra={
                "jobId": job_id,
                "eventId": event_id,
                "status": outcome.status,
                "model": outcome.model_used,
                "costUsd": round(outcome.cost_usd, 4),
                **log_fields(outcome.usage),
            },
        )
        return job_id


def judge_policy(store: JobStore, raw_event: dict[str, Any], model: Any = None, regions: Any = None) -> str | None:
    """정책 수집 이벤트 → 판정 틀(창업지원·사업공간 모집)을 담은 extraction.completed를 아웃박스에 넣고 그 eventId.
    model이 있으면 AI로 공고 글을 읽고(정책 공고는 PDF 없이 글만 옴), 없거나 읽기에 실패하면 K-Startup 구간 칸 규칙으로 만듭니다(그 틀은 IN_REVIEW).
    판정 틀이 없는 분야(BENEFIT), 틀·지원 지역을 정하지 못한 정책, 이미 넣은 수집 이벤트면 None.
    전체 비용 상한에 걸리면 BudgetExhausted(큐로 되돌림), AI 일시 실패(로컬 AI 연결 실패 포함)면 AiUnavailable(큐로 되돌림),
    AI 영구 실패 뒤 구간 칸 규칙으로도 보낼 것을 만들지 못하면 AiFailed(.dlq), 만든 이벤트가 계약에 맞지 않으면 ValueError(.dlq)."""
    payload = raw_event.get("payload") if isinstance(raw_event.get("payload"), dict) else {}
    if payload.get("field") not in POLICY_FIELDS or store.judged(raw_event):
        return None
    reading = None
    failed: str | None = None
    if model is not None:
        try:
            reading = read_policy(payload, model)
        except ModelError as error:
            if error.code == "GLOBAL_BUDGET":
                raise BudgetExhausted(str(error)) from error
            if error.transient or error.code in POLICY_RETRY_CODES:
                raise AiUnavailable(error.code or "transient") from error
            failed = error.code or "unknown"
            log.warning("정책 글을 AI로 읽지 못해 구간 칸 규칙으로 만듭니다", extra={"code": error.code, "rawPolicyId": payload.get("rawPolicyId")})
    frame, frame_reason, by_rules = policy_frame_detail(payload, reading, regions)
    completed = policy_completed_payload(payload, frame, regions, reading, by_rules=by_rules)
    if completed is None:
        if failed is not None:  # AI가 읽지 못해 못 만든 것: 조용히 ack하면 기록이 남지 않음(리뷰 2026-10-22)
            raise AiFailed(failed)
        # 까닭을 나눠 남김(기준일 확인 실패·틀 검사 실패·지역 미정 …). 예전엔 이유 없이 조용히 넘어갔음(리뷰 2026-10-23)
        reason = not_sent_reason(payload, frame, frame_reason, regions, reading)
        log.info("정책 판정 틀을 보내지 않습니다", extra={"rawPolicyId": payload.get("rawPolicyId"), "field": payload.get("field"), "reason": reason})
        return None
    event = {**new_event(EVENT_TYPE, PRODUCER, completed), "traceId": raw_event.get("traceId")}
    if errors := tools().validate(event, COMPLETED_SCHEMA):
        raise ValueError(f"정책 판정 이벤트가 계약에 맞지 않습니다: {errors[:3]}")
    if not store.save_judgment(raw_event, event):
        return None
    log.info(
        "정책 판정 틀 발행 대기",
        extra={
            "eventId": event["eventId"],
            "field": completed["field"],
            "rawPolicyId": completed["rawPostId"],
            "ai": not by_rules,
            "reviewStatus": completed["reviewStatus"],
        },
    )
    return event["eventId"]


def judge_benefit(store: JobStore, raw_event: dict[str, Any], model: Any, regions: Any = None) -> str | None:
    """주거·이주 혜택 정책 수집 이벤트 → policy.extracted를 아웃박스에 넣고 그 eventId. 이미 넣은 수집 이벤트면 None.
    AI로 글을 읽고(관련성·요약·지원 내용·일정·조건), 출처 코드 칸(온통청년)은 규칙으로 옮겨 규칙 값을 우선합니다(benefit/).
    전체 비용 상한이면 BudgetExhausted, AI 일시 실패면 AiUnavailable(큐로 되돌림), AI 영구 실패면 AiFailed(.dlq),
    만든 이벤트가 계약에 맞지 않으면 ValueError(.dlq)."""
    payload = raw_event.get("payload") if isinstance(raw_event.get("payload"), dict) else {}
    if payload.get("field") not in BENEFIT_FIELDS or store.judged(raw_event):
        return None
    try:
        reading = read_benefit(payload, model)
    except ModelError as error:
        if error.code == "GLOBAL_BUDGET":
            raise BudgetExhausted(str(error)) from error
        if error.transient or error.code in POLICY_RETRY_CODES:
            raise AiUnavailable(error.code or "transient") from error
        raise AiFailed(error.code or "unknown") from error
    rules = rules_for(str(payload.get("sourceCode") or ""), payload.get("record"), str(payload.get("text") or ""))
    extracted = build_payload(payload, reading, rules, regions)
    event = {**new_event(BENEFIT_EVENT_TYPE, PRODUCER, extracted), "traceId": raw_event.get("traceId")}
    if errors := tools().validate(event, BENEFIT_SCHEMA):
        raise ValueError(f"혜택 정제 이벤트가 계약에 맞지 않습니다: {errors[:3]}")
    if not store.save_benefit(raw_event, event):  # 결과를 쌓고, 확인 필요면 검수 대기로(관리자 혜택 검수)
        return None
    log.info(
        "혜택 정제 결과 발행 대기",
        extra={
            "eventId": event["eventId"],
            "rawPolicyId": extracted["rawPolicyId"],
            "relevant": extracted["relevant"],
            "conditions": len(extracted["conditions"]),
            "needsReview": extracted["quality"]["needsReview"],
        },
    )
    return event["eventId"]


@contextmanager
def store_session(settings: Settings):
    conn = db.connect(settings.db_url)
    try:
        yield JobStore(conn)
    finally:
        conn.close()


# 검수 API가 기다릴 수 있는 최대 시간. api가 검수 API를 5초 기다리므로 그 안에 끝나게
REVIEW_POOL_TIMEOUT_SECONDS = 4.0


def review_pool(settings: Settings) -> ConnectionPool:
    """검수 API용 DB 연결 풀. 요청마다 새로 연결(운영은 TLS)하지 않고, 동시에 여는 연결 수도 max_size로 묶어요.
    끊긴 연결은 내주기 전에 확인해 바꿔요(check)."""
    return ConnectionPool(
        settings.db_url,
        min_size=1,
        max_size=settings.review_db_pool,
        timeout=REVIEW_POOL_TIMEOUT_SECONDS,
        kwargs={"application_name": "mujuthaek", "autocommit": True},
        check=ConnectionPool.check_connection,
        name="review-api",
        open=True,
    )


@contextmanager
def pooled_store_session(pool: ConnectionPool):
    with pool.connection() as conn:
        yield JobStore(conn)


def relay_loop(settings: Settings, stop: threading.Event, health: Health | None = None) -> None:
    """stop이 설정될 때까지 아웃박스 이벤트를 relay_seconds마다 발행합니다. 오류가 나면 5초 뒤 다시 연결합니다."""
    while not stop.is_set():
        try:
            conn = db.connect(settings.db_url)
            conn.autocommit = True
            connection = broker.connect(settings.rabbitmq_url)
            channel = outbox.open_channel(connection)  # 확인 모드: 브로커가 받았다고 확인한 것만 "보냄"으로 기록
            while not stop.is_set():
                sent = outbox.relay_once(conn, channel)
                if health:
                    health.beat("relay")
                if sent:
                    log.info("이벤트 발행", extra={"count": sent})
                connection.process_data_events(time_limit=settings.relay_seconds)
        except Exception:
            log.exception("아웃박스 발행 오류. 5초 뒤 다시 연결합니다")
            stop.wait(5)


CONSUMER_BEAT_SECONDS = 30


def judge_message(settings: Settings, processor: Processor, raw_event: dict[str, Any], retries: RetryCounter, why: list[str] | None = None) -> str:
    """정책 수집 이벤트 하나 → "ack"·"requeue"·"dlq". 창업지원·사업공간이면 판정 틀 이벤트를 넣고 ack, 전체 비용 상한·DB 장애·AI 일시
    실패면 requeue, AI 일시 실패가 retries.limit번 이어지거나 AI 영구 실패로 틀을 못 만들었거나 계약 위반이면 .dlq.
    why를 주면 .dlq일 때 이유 코드(AI_RETRY_EXHAUSTED:코드 · AI_FAILED:코드 · ERROR:예외 종류)를 넣습니다."""
    payload = raw_event.get("payload") if isinstance(raw_event.get("payload"), dict) else {}
    benefit = payload.get("field") in BENEFIT_FIELDS and getattr(settings, "benefit_enabled", False)
    if payload.get("field") not in POLICY_FIELDS and not benefit:  # 혜택 정제가 꺼져 있으면 BENEFIT: 비용 장부·DB를 열지 않고 넘김
        return "ack"
    key = _policy_retry_key(raw_event)
    trace = {"eventId": raw_event.get("eventId"), "rawPolicyId": payload.get("rawPolicyId"), "rawVersion": payload.get("version")}
    try:
        ledger = processor.open_ledger(raw_event)
        try:
            if ledger is not None and (reason := ledger.room(settings.notice_budget_usd)):
                raise BudgetExhausted(reason)
            models = processor.models.for_notice(ledger=ledger)
            model = FallbackOnErrorModel(models.primary, models.fallback) if models.fallback is not None else models.primary
            with store_session(settings) as store:
                if benefit:
                    judge_benefit(store, raw_event, model, processor.regions)
                else:
                    judge_policy(store, raw_event, model, processor.regions)
        finally:
            if ledger is not None:
                ledger.close()
    except BudgetExhausted as reason:
        log.warning("전체 비용 상한에 닿아 정책 처리를 미룹니다", extra={"reason": str(reason)})
        time.sleep(BUDGET_WAIT_SECONDS)
        return "requeue"
    except AiUnavailable as reason:
        if retries.fail(key):
            log.warning("AI 호출이 연속으로 일시 실패해 .dlq로 보냅니다", extra={"code": str(reason), "failures": retries.limit, **trace})
            _note(why, f"AI_RETRY_EXHAUSTED:{reason}")
            return "dlq"
        log.warning("AI 호출이 일시적으로 실패해 잠시 뒤 큐로 되돌립니다", extra={"code": str(reason), **trace})
        time.sleep(DB_RETRY_SECONDS)
        return "requeue"
    except AiFailed as reason:
        retries.clear(key)
        log.warning("AI가 정책 글을 읽지 못했고 구간 칸 규칙으로도 판정 틀을 만들지 못해 .dlq로 보냅니다", extra={"code": str(reason), **trace})
        _note(why, f"AI_FAILED:{reason}")
        return "dlq"
    except _db_errors():
        log.exception("DB를 쓸 수 없어 잠시 뒤 큐로 되돌립니다")
        time.sleep(DB_RETRY_SECONDS)
        return "requeue"
    except Exception as error:
        retries.clear(key)
        log.exception("판정 틀을 만들지 못했습니다. .dlq로 보냅니다")
        _note(why, f"ERROR:{type(error).__name__}")
        return "dlq"
    retries.clear(key)
    return "ack"


def consume(settings: Settings, processor: Processor, health: Health | None = None) -> None:
    """큐를 선언하고 메시지를 한 번에 하나씩 받아 처리합니다. 처리는 별도 스레드에서 하고 확인 응답은 연결 스레드로 넘깁니다."""
    connection = broker.connect(settings.rabbitmq_url)
    channel = connection.channel()
    declare(channel)
    channel.basic_qos(prefetch_count=1)
    alerts = QuietAlerts(SlackNotifier(settings.slack_webhook_url), "extraction")  # 실패 큐로 보낼 때 운영 알림

    def finish(delivery_tag: int, decision: str) -> None:
        if decision == "ack":
            channel.basic_ack(delivery_tag)
        elif decision == "requeue":
            channel.basic_nack(delivery_tag, requeue=True)  # DB 장애: 큐로 되돌려 나중에 다시
        else:
            channel.basic_nack(delivery_tag, requeue=False)  # 재시도 없이 .dlq로

    def work(delivery_tag: int, body: bytes) -> None:
        """메시지 하나를 처리하고 결과에 따라 ack, DB 장애면 requeue, JSON이 아니거나 저장 실패면 .dlq로 정합니다."""
        decision = "ack"
        try:
            raw_event = json.loads(body)
            if not isinstance(raw_event, dict):
                raise ValueError("이벤트가 객체가 아닙니다.")
            with store_session(settings) as store:
                processor.handle(store, raw_event)
        except BudgetExhausted as reason:
            log.warning("전체 비용 상한에 닿아 처리를 미룹니다", extra={"reason": str(reason)})
            time.sleep(BUDGET_WAIT_SECONDS)
            decision = "requeue"
        except ClaimBusy as busy:
            log.info("같은 원본 버전을 다른 처리가 하고 있어 잠시 뒤 큐로 되돌립니다", extra={"claim": str(busy)})
            time.sleep(CLAIM_BUSY_SECONDS)
            decision = "requeue"
        except _db_errors():
            log.exception("DB를 쓸 수 없어 잠시 뒤 큐로 되돌립니다")
            time.sleep(DB_RETRY_SECONDS)
            decision = "requeue"
        except ValueError:
            log.warning("JSON 이벤트가 아니어서 .dlq로 보냅니다")
            decision = "dlq"
            alerts.send("dlq:notice", f"공고 메시지를 실패 큐로 보냈어요 ({DLQ})", "INVALID_EVENT")
        except Exception as error:
            log.exception("저장 실패. .dlq로 보냅니다")
            decision = "dlq"
            alerts.send("dlq:notice", f"공고 메시지를 실패 큐로 보냈어요 ({DLQ})", f"ERROR:{type(error).__name__}")
        connection.add_callback_threadsafe(functools.partial(finish, delivery_tag, decision))

    def on_message(_channel, method, _properties, body: bytes) -> None:
        threading.Thread(target=work, args=(method.delivery_tag, body), daemon=True).start()

    retries = RetryCounter()

    def judge(delivery_tag: int, body: bytes, properties: Any = None) -> None:
        """정책 수집 이벤트 하나를 judge_message로 처리하고 그 결정(ack·requeue·.dlq)을 연결 스레드로 넘깁니다."""
        why: list[str] = []
        raw_event: Any = None
        try:
            raw_event = json.loads(body)
            if not isinstance(raw_event, dict):
                raise ValueError("이벤트가 객체가 아닙니다.")
            decision = judge_message(settings, processor, raw_event, retries, why)
        except Exception as error:
            log.exception("판정 틀을 만들지 못했습니다. .dlq로 보냅니다")
            decision = "dlq"
            why.append("INVALID_EVENT" if isinstance(error, ValueError) else f"ERROR:{type(error).__name__}")
        reason = why[-1] if why else None
        if decision == "dlq":
            payload = raw_event.get("payload") if isinstance(raw_event, dict) and isinstance(raw_event.get("payload"), dict) else {}
            alerts.send(
                "dlq:policy",
                f"정책 메시지를 실패 큐로 보냈어요 ({POLICY_DLQ})",
                f"{reason} · {payload.get('field')} rawPolicyId={payload.get('rawPolicyId')} v{payload.get('version')}",
            )
        connection.add_callback_threadsafe(functools.partial(finish_policy, channel, delivery_tag, decision, body, properties, reason))

    def on_policy(_channel, method, properties, body: bytes) -> None:
        threading.Thread(target=judge, args=(method.delivery_tag, body, properties), daemon=True).start()

    def tick() -> None:  # 연결 스레드가 살아 메시지를 받을 수 있는 동안 신호를 보냅니다(AI 처리는 다른 스레드라 막히지 않음)
        if health:
            health.beat("consumer")
        connection.call_later(CONSUMER_BEAT_SECONDS, tick)

    channel.basic_consume(queue=QUEUE, on_message_callback=on_message)
    channel.basic_consume(queue=POLICY_QUEUE, on_message_callback=on_policy)
    log.info("큐 소비 시작", extra={"queue": QUEUE, "model": processor.models.describe()})
    tick()
    channel.start_consuming()


def purge_call_cache(settings: Settings, store: JobStore) -> int:
    """보관 기간(EXTRACTION_CALL_CACHE_DAYS)이 지난 저장 응답을 지웁니다. 캐시를 끈 설정이면 아무것도 하지 않습니다."""
    if not settings.call_cache:
        return 0
    removed = PostgresCallCache(store.conn).purge(settings.call_cache_days)
    if removed:
        log.info("오래된 호출 캐시 삭제", extra={"count": removed, "days": settings.call_cache_days})
    return removed


@contextmanager
def beating(health: Health | None, name: str, every: float = CONSUMER_BEAT_SECONDS):
    """긴 처리 동안 every초마다 health 신호를 보냅니다."""
    if health is None:
        yield
        return
    stop = threading.Event()

    def beat() -> None:
        while not stop.wait(every):
            health.beat(name)

    thread = threading.Thread(target=beat, daemon=True)
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join(timeout=5)


def retry_loop(settings: Settings, processor: Processor, stop: threading.Event, health: Health | None = None) -> None:
    """자료 대기(WAITING_SOURCE)·실패(FAILED)를 점점 길게 기다리며 다시 처리합니다(최대 settings.max_attempts번).
    예전엔 사람이 retry 명령을 돌려야만 다시 처리돼, PDF가 1분 늦게 올라와도 공고가 계속 대기에 남았습니다(검토 2026-10-16)."""
    while not stop.wait(settings.retry_seconds):
        if health:
            health.beat("retry")
        try:
            with store_session(settings) as store:
                purge_call_cache(settings, store)
                events = store.retryable_events(limit=10, max_attempts=settings.max_attempts, base_delay_seconds=settings.retry_seconds)
                for raw_event in events:
                    try:
                        # 한 건이 30분 넘게 걸리기도 해서, 처리하는 동안에도 신호를 보냅니다(예전엔 /health가 503이 되어 재시작될 수 있었음)
                        with beating(health, "retry"):
                            processor.handle(store, raw_event)
                    except ClaimBusy:
                        log.info("다른 처리가 하고 있어 다음 차례에 다시 봅니다")
                    except BudgetExhausted as reason:
                        log.warning("전체 비용 상한에 닿아 다시 처리를 다음 차례로 미룹니다", extra={"reason": str(reason)})
                        break
        except Exception:
            log.exception("다시 처리 중 오류. 다음 차례에 다시 봅니다")


def run(settings: Settings) -> None:
    """발행·다시 처리·검수 API를 백그라운드 스레드로 띄우고, 큐 소비를 연결이 끊길 때마다 다시 붙여 계속 돌립니다."""
    processor = Processor(settings)
    stop = threading.Event()
    # 부분마다 이 초 안에 신호가 없으면 /health가 503 (발행기는 2초마다, 소비자는 30초마다, 다시 처리는 retry_seconds마다 신호)
    health = Health({"consumer": 120, "relay": 120, "retry": settings.retry_seconds * 2 + 60})
    threading.Thread(target=relay_loop, args=(settings, stop, health), daemon=True, name="relay").start()
    threading.Thread(target=retry_loop, args=(settings, processor, stop, health), daemon=True, name="retry").start()
    pool = review_pool(settings)
    service = ReviewService(lambda: pooled_store_session(pool), new_event, settings.monthly_budget_usd)
    server = serve(service, settings.review_host, settings.review_port, settings.review_token, health)
    threading.Thread(target=server.serve_forever, daemon=True, name="review-api").start()
    log.info("검수 API 시작", extra={"host": settings.review_host, "port": settings.review_port})
    while True:  # 큐 연결이 끊기면 다시 붙습니다
        try:
            consume(settings, processor, health)
        except KeyboardInterrupt:
            stop.set()
            server.shutdown()
            pool.close()
            return
        except Exception:
            log.exception("큐 연결 오류. 5초 뒤 다시 연결합니다")
            time.sleep(5)
