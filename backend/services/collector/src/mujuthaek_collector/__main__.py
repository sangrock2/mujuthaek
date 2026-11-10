"""수집 워커 실행 명령.

  python -m mujuthaek_collector run                       스케줄러로 계속 실행 (운영·Docker 기본 명령)
  python -m mujuthaek_collector run-once dcco             출처 하나를 지금 한 번 수집
  python -m mujuthaek_collector run-once dcco --recheck   마감 전 공고까지 다시 열어 정정 확인
  python -m mujuthaek_collector run-all                   모든 출처를 순서대로 한 번
  python -m mujuthaek_collector run-once gov24            정책 API 출처 하나 (gov24, bokjiro_central, bokjiro_local, youth)
  python -m mujuthaek_collector run-policies              정책 API 출처를 순서대로 한 번
  python -m mujuthaek_collector relay                     아웃박스에 쌓인 이벤트를 한 번 보내기
  python -m mujuthaek_collector cleanup                   보관 기한이 지난 원본 파일 지우기
  python -m mujuthaek_collector save-fixtures dcco        테스트용 화면 저장 (tests/fixtures/dcco/)
  python -m mujuthaek_collector status                    최근 수집 회차 보기
  python -m mujuthaek_collector intake                    처음 수집 개수 제한: 묶음마다 고른 결과·기다리는 글 보기
  python -m mujuthaek_collector intake --decide           기다리는(HELD) 글에서 지금 고르기 (보통은 수집기가 알아서 해요)
  python -m mujuthaek_collector area-upload --source BUS_STOP --data-date 2025-10-31 --file … [--scope 강원]
                                                          생활권·상권 원천 파일을 S3 area/에 올리고 적재 요청 보내기
  python -m mujuthaek_collector area-upload --manifest area/area_manifest.csv --skip-upload
  python -m mujuthaek_collector area-upload --manifest area/area_manifest_address.csv --skip-upload --resend   빠진 적재 다시 요청
                                                          이미 올린 파일 목록으로 적재 요청만 보내기

스케줄 (서울 시간). 운영 서버는 낮(09~18시, 11/7부터 10~19시)에만 켜져 있어서 하루 한 번 작업은 모두 11시대예요
  평일 9~19시 매시 5분   모든 출처 수집 (출처마다 따로, 동시에 COLLECTOR_PARALLEL_SOURCES개까지. 앞 회차가 안 끝난 출처만 이번 차례를 건너뜀)
  매일 11시              정책 API 수집 (목록 전체 → 새 정책·바뀐 정책만 상세·첨부)
  매일 11시 30분         정정 확인 (마감 전 공고를 다시 열어 바뀌었으면 새 버전)
  매일 11시 50분         보관 기한이 지난 원본 파일 정리
  매일 12시 30분         처음 수집 고르기 (아직 고르지 않은 묶음만. 다 골랐으면 아무것도 안 해요)
  금요일 13시            정책 다시 확인 (목록에 수정일이 없는 복지로 중앙만. 주말엔 서버가 꺼져 있을 수 있어요)

처음 수집 개수 제한 (core/intake.py)
  배포 뒤 처음 뜰 때 모든 출처 목록을 읽어 새 글을 HELD로 두고, 묶음마다 최신 N개만 골라 AI 추출로 보내요
  (LH 주거 10 · 다른 주거 10 · 사업공간 10 · 지원 정책 500, COLLECTOR_INTAKE_*). 나머지는 IGNORED로 쓰지 않아요
  꺼져 있던 동안 지난 시각의 작업은 건너뛰어요(misfire_grace_time 10분). 매시 수집·다음 날 같은 작업이 이어받아요
  5초마다                아웃박스 이벤트 발행
"""

from __future__ import annotations

import argparse
import json
import logging
import threading
from concurrent.futures import Executor, ThreadPoolExecutor
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from mujuthaek_collector.area.sources import SOURCES as AREA_SOURCES
from mujuthaek_collector.config import Settings
from mujuthaek_collector.core import intake
from mujuthaek_collector.core.file_store import S3FileStore
from mujuthaek_collector.core.http_client import PoliteClient
from mujuthaek_collector.core.locks import SourceLocks
from mujuthaek_collector.core.storage import PostgresStore
from mujuthaek_collector.pipeline import RunResult, run_source
from mujuthaek_collector.sources.base import Fetcher, Source
from mujuthaek_collector.sources.policy.config import PolicySettings
from mujuthaek_collector.sources.policy.pipeline import run_policy_source
from mujuthaek_collector.sources.policy.registry import POLICY_ORDER, build_policy_sources, get_policy
from mujuthaek_collector.sources.policy.store import PostgresPolicyStore
from mujuthaek_collector.sources.registry import ORDER, get
from mujuthaek_platform import broker, outbox
from mujuthaek_platform import logging as platform_logging
from mujuthaek_platform.slack import QuietAlerts

log = logging.getLogger("mujuthaek_collector")
TIMEZONE = "Asia/Seoul"
HEALTH_PORT = 8091
FIXTURES = Path(__file__).resolve().parents[2] / "tests" / "fixtures"
_last_results: dict[str, dict] = {}  # 상태 확인(/health)에 보여줄 출처별 마지막 결과
_locks = SourceLocks()  # 같은 출처만 겹치지 않게 (출처끼리는 서로 막지 않아요)


def make_client(source: Source, settings: Settings) -> Fetcher:
    custom = source.make_client(settings)
    if custom is not None:
        return custom
    return PoliteClient(delay_seconds=settings.delay_seconds, legacy_tls=source.legacy_tls, max_file_bytes=settings.max_file_bytes)


def make_file_store(settings: Settings) -> S3FileStore:
    return S3FileStore(settings.s3_bucket, settings.s3_endpoint, settings.s3_access_key, settings.s3_secret_key)


def collect(code: str, settings: Settings, *, recheck: bool = False) -> RunResult:
    source = get(code)
    store = PostgresStore(settings.db_url)
    files = make_file_store(settings)
    client = make_client(source, settings)
    try:
        result = run_source(source, client, store, files, settings, recheck=recheck)
    finally:
        client.close()
        store.close()
    _last_results[code] = {"status": result.status, "new": result.new_count, "at": datetime.now().isoformat(timespec="seconds")}
    alert_on_trouble(code, result)
    return result


FAILURE_ALERT_RUNS = 3  # 같은 출처가 이만큼 연달아 실패(FAILED·BLOCKED)하면 슬랙으로 한 번 알려요
_failure_runs: dict[str, int] = {}  # 출처별 연속 실패 수(이 프로세스 안에서만. 다시 뜨면 처음부터)
_alerts: QuietAlerts | None = None


def alerts() -> QuietAlerts:
    global _alerts
    if _alerts is None:
        _alerts = QuietAlerts.from_env("collector")
    return _alerts


def alert_on_trouble(code: str, result: RunResult) -> None:
    """연속 실패가 FAILURE_ALERT_RUNS번이 되는 순간과, 목록이 계속 비어 사이트 구조 변경이 의심될 때 운영 알림을 보내요."""
    if result.status in ("FAILED", "BLOCKED"):
        _failure_runs[code] = _failure_runs.get(code, 0) + 1
        if _failure_runs[code] == FAILURE_ALERT_RUNS:
            alerts().send(f"source.failed:{code}", f"{code} 수집이 {FAILURE_ALERT_RUNS}번 연달아 실패했어요", "\n".join(result.warnings[-3:]))
    else:
        _failure_runs[code] = 0
    suspected = [w for w in result.warnings if "구조 변경 의심" in w]
    if suspected:
        alerts().send(f"source.structure:{code}", f"{code} 사이트 구조가 바뀐 것 같아요", "\n".join(suspected[:3]))


def enabled_sources(settings: Settings, order: list[str] = ORDER) -> list[str]:
    """sources.enabled가 true인 출처만 order 순서대로. 문제가 생긴 출처는 DB에서 false로 바꿔 잠시 멈춰요."""
    store = PostgresStore(settings.db_url)
    try:
        enabled = {row[0] for row in store.conn.execute("select code from sources where enabled").fetchall()}
    finally:
        store.close()
    return [code for code in order if code in enabled]


def collect_locked(code: str, settings: Settings, *, recheck: bool = False, run=None) -> None:
    """출처 하나를 그 출처 잠금 안에서. 앞 회차가 아직 돌고 있으면 이번 차례만 건너뛰어요(다른 출처는 그대로 돌아요)."""
    if not _locks.acquire(code):
        log.warning("이 출처의 이전 수집이 아직 끝나지 않아 이번 차례는 건너뛰어요", extra={"source": code})
        return
    try:
        (run or collect)(code, settings, recheck=recheck)
    except Exception:  # noqa: BLE001 — 한 출처의 실패가 다른 출처를 막지 않게
        log.exception("출처 수집 실패", extra={"source": code})
    finally:
        _locks.release(code)


def collect_all(settings: Settings, *, recheck: bool = False, pool: Executor | None = None) -> None:
    """게시판 출처를 출처마다 따로 수집해요. pool을 주면(스케줄러) 거기에 맡기고 바로 돌아와서, 느린 출처가 다음 회차 전체를 막지 않아요.
    없으면(run-all) 동시에 settings.parallel_sources개까지 돌리고 다 끝날 때까지 기다려요."""
    codes = enabled_sources(settings)
    if pool is not None:
        for code in codes:
            pool.submit(collect_locked, code, settings, recheck=recheck)
        return
    with ThreadPoolExecutor(max_workers=settings.parallel_sources, thread_name_prefix="collect") as own:
        for code in codes:
            own.submit(collect_locked, code, settings, recheck=recheck)


def collect_policy(code: str, settings: Settings, *, recheck: bool = False) -> RunResult:
    """정책 API 출처 하나. API는 짧은 간격, 원문 화면·첨부는 기관 사이트라 게시판 수집과 같은 간격(robots.txt 확인)으로 요청해요."""
    policy_settings = PolicySettings.from_env()
    source = get_policy(code, policy_settings)
    store = PostgresPolicyStore(settings.db_url)
    files = make_file_store(settings)
    api = PoliteClient(delay_seconds=policy_settings.api_delay_seconds, max_file_bytes=settings.max_file_bytes)
    web = PoliteClient(delay_seconds=settings.delay_seconds, max_file_bytes=settings.max_file_bytes)
    try:
        result = run_policy_source(source, api, web, store, files, policy_settings, recheck=recheck)
    finally:
        api.close()
        web.close()
        store.close()
    _last_results[code] = {"status": result.status, "new": result.new_count, "at": datetime.now().isoformat(timespec="seconds")}
    alert_on_trouble(code, result)
    return result


def collect_policies(settings: Settings, *, weekly_recheck: bool = False) -> None:
    """정책 출처를 순서대로(하루 한 번). 게시판 수집과는 서로 막지 않고, 같은 정책 출처만 겹치지 않게 출처 잠금을 잡아요.
    weekly_recheck=True면 목록에 수정일이 없는 출처만 전부 다시 열어봐요."""
    sources = build_policy_sources(PolicySettings.from_env())
    for code in enabled_sources(settings, POLICY_ORDER):
        if weekly_recheck and not sources[code].weekly_recheck:
            continue
        collect_locked(code, settings, recheck=weekly_recheck, run=collect_policy)


class Relay:
    """아웃박스 발행기. DB·RabbitMQ 연결을 유지하고, 끊기면 다음 차례에 다시 연결해요."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.store: PostgresStore | None = None
        self.connection = None
        self.channel = None

    def once(self) -> int:
        try:
            if self.store is None:
                self.store = PostgresStore(self.settings.db_url)
            if self.connection is None or self.connection.is_closed:
                self.connection = broker.connect(self.settings.rabbitmq_url)
                self.channel = outbox.open_channel(self.connection)  # 확인 모드: 브로커가 받았다고 답해야 보낸 것으로 쳐요
            self.connection.process_data_events(0)  # 보낼 게 없을 때도 RabbitMQ 연결 확인(heartbeat)을 처리해요
            return outbox.relay_once(self.store.conn, self.channel)
        except Exception:
            self.close()  # 다음 차례에 새로 연결
            raise

    def quietly(self) -> None:
        try:
            self.once()
        except Exception:  # noqa: BLE001 — RabbitMQ가 잠깐 내려가도 다음 차례에 다시 보내요 (아웃박스에 남아 있음)
            log.exception("이벤트 발행 실패")

    def close(self) -> None:
        for closer in (lambda: self.connection and self.connection.close(), lambda: self.store and self.store.close()):
            try:
                closer()
            except Exception:  # noqa: BLE001
                pass
        self.store = self.connection = self.channel = None


def relay(settings: Settings) -> int:
    """명령줄에서 한 번만 보낼 때."""
    relayer = Relay(settings)
    try:
        return relayer.once()
    finally:
        relayer.close()


def cleanup(settings: Settings, today: date | None = None) -> int:
    """보관 기한(stored_until)이 지난 원본 파일만 S3에서 지워요. 다운로드 주소·해시·추출한 글자는 남아요."""
    files = make_file_store(settings)
    removed = 0
    for store in (PostgresStore(settings.db_url), PostgresPolicyStore(settings.db_url)):  # 게시판 첨부(raw_files)와 정책 첨부(raw_policy_files)
        try:
            for file_id, key in store.expired_files(today or date.today()):
                files.delete(key)
                store.mark_file_deleted(file_id)
                removed += 1
        finally:
            store.close()
    log.info("보관 기한 정리", extra={"removed": removed})
    return removed


def save_fixtures(code: str, settings: Settings, details: int) -> None:
    """테스트용 화면 저장: 게시판마다 목록 1페이지와 상세 몇 건을 tests/fixtures/<출처>/에 그대로 저장해요."""
    source = get(code)
    folder = FIXTURES / code
    folder.mkdir(parents=True, exist_ok=True)
    client = make_client(source, settings)
    try:
        for board in source.boards:
            request = source.list_request(board, 1)
            body = client.text(request.url, data=request.data, referer=request.referer)
            ext = "json" if body.lstrip().startswith("{") else "html"
            (folder / f"{board.key}-list.{ext}").write_text(body, encoding="utf-8")
            for item in source.parse_list(board, body, request.url)[:details]:
                detail = source.detail_request(item)
                page = client.text(detail.url, data=detail.data, referer=detail.referer)
                (folder / f"{board.key}-detail-{item.post_key}.html").write_text(page, encoding="utf-8")
                print(f"저장: {folder.name}/{board.key}-detail-{item.post_key}.html  {item.title[:40]}")
    finally:
        client.close()


def decide_intake(settings: Settings) -> list[intake.Decision]:
    """아직 고르지 않은 묶음을 HELD 글에서 골라요."""
    store = PostgresStore(settings.db_url)
    try:
        return intake.decide(store.conn, settings.intake_limits)
    finally:
        store.close()


def first_intake(settings: Settings) -> None:
    """수집기가 뜰 때: 아직 고르지 않은 묶음이 있으면 모든 출처 목록을 읽고(새 글은 HELD) 골라서, 고른 글을 바로 수집해요.
    다 골랐으면 아무것도 안 해요. 출처 잠금을 같이 써서 스케줄 회차와 겹치지 않아요."""
    store = PostgresStore(settings.db_url)
    try:
        waiting = intake.undecided(store.conn)
    finally:
        store.close()
    if not waiting:
        return
    log.info("처음 수집: 목록을 읽고 묶음마다 최신 글만 골라요", extra={"groups": waiting})
    collect_all(settings)
    collect_policies(settings)
    decisions = decide_intake(settings)
    left = [g for g in waiting if g not in {d.group for d in decisions}]
    if left:
        log.warning("처음 수집에서 아직 읽은 글이 없어 고르지 못한 묶음이 있어요. 매일 12시 30분에 다시 골라요", extra={"groups": left})
    if decisions:
        collect_all(settings)  # 고른 글(PENDING)을 바로 열어요. 남은 건 다음 회차에
        collect_policies(settings)


def print_intake(settings: Settings, decide: bool) -> None:
    if decide:
        for d in decide_intake(settings):
            print(f"골랐어요: {d.group} 남김 {d.kept}/{d.limit}, 안 씀 {d.ignored}, 기준일 {d.cutoff_on or '-'}")
    store = PostgresStore(settings.db_url)
    try:
        for line in intake.summary(store.conn):
            print(line)
    finally:
        store.close()


def print_status(settings: Settings) -> None:
    store = PostgresStore(settings.db_url)
    try:
        rows = store.conn.execute(
            "select source_code, started_at, finished_at, status, new_count, left(coalesce(error, ''), 120) from crawl_runs order by started_at desc limit 20"
        ).fetchall()
    finally:
        store.close()
    for code, started, finished, status, new, error in rows:
        took = f"{(finished - started).seconds}초" if finished else "진행 중"
        print(f"{started:%m-%d %H:%M}  {code:5}  {status:8}  새 {new:3}건  {took:>6}  {error}")


def area_upload(args: argparse.Namespace, settings: Settings) -> int:
    """원천 파일 올리기(또는 목록으로 확인만) → 받는 큐 만들기 → 아웃박스 기록 → 발행. 문제가 있으면 1을 돌려줘요."""
    from mujuthaek_collector.area import command

    connection = broker.connect(settings.rabbitmq_url)
    try:
        command.declare_receiver(connection.channel())
    finally:
        connection.close()
    store = PostgresStore(settings.db_url)
    files = make_file_store(settings)
    try:
        if args.manifest:
            result = command.from_manifest(files, store.conn, Path(args.manifest), args.resend)
        else:
            data_date = date.fromisoformat(args.data_date)
            result = command.upload_file(files, store.conn, args.source, data_date, Path(args.file), args.scope, args.resend)
    finally:
        store.close()
    if args.resend:
        print(f"올림 {result.uploaded}개, 적재 요청 다시 보냄 {result.recorded}건 (이미 적재한 파일은 api가 SKIPPED로 걸러요)")
    else:
        print(f"올림 {result.uploaded}개, 적재 요청 기록 {result.recorded}건 (같은 파일은 다시 올리거나 기록하지 않아요)")
    if result.archived:
        print(f"보관만 하는 원본 {result.archived}줄은 적재 대상이 아니라 건너뛰었어요")
    for problem in result.problems:
        print(f"  - {problem}")
    print(f"이벤트 발행: {relay(settings)}건")
    return 1 if result.problems else 0


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 — http.server 규칙
        if self.path != "/health":
            self.send_response(404)
            self.end_headers()
            return
        body = json.dumps({"status": "UP", "sources": _last_results}, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):  # 상태 확인 요청은 로그에 남기지 않아요
        pass


def serve_health() -> None:
    server = HTTPServer(("0.0.0.0", HEALTH_PORT), HealthHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()


def run_scheduler(settings: Settings) -> None:
    from apscheduler.schedulers.blocking import BlockingScheduler

    from mujuthaek_collector import admin_api

    serve_health()
    admin_api.serve(settings.db_url, admin_api.Runner(_locks, collect, collect_policy, POLICY_ORDER, settings))  # 관리자 수집 현황 API (:8093)
    scheduler = BlockingScheduler(timezone=TIMEZONE)
    common = {"max_instances": 1, "coalesce": True, "misfire_grace_time": 600}
    # 게시판 출처는 이 풀에서 동시에 돌아요. 회차 작업은 맡기고 바로 끝나서 다음 회차가 밀리지 않아요
    pool = ThreadPoolExecutor(max_workers=settings.parallel_sources, thread_name_prefix="collect")
    # 운영 서버가 켜져 있는 낮 시간에 맞춰요 (09~18시, 11/7부터 10~19시)
    scheduler.add_job(collect_all, "cron", day_of_week="mon-fri", hour="9-19", minute=5, args=[settings], kwargs={"pool": pool}, id="collect", **common)
    scheduler.add_job(collect_policies, "cron", hour=11, minute=0, args=[settings], id="policies", **common)
    scheduler.add_job(collect_all, "cron", hour=11, minute=30, args=[settings], kwargs={"recheck": True, "pool": pool}, id="recheck", **common)
    scheduler.add_job(cleanup, "cron", hour=11, minute=50, args=[settings], id="cleanup", **common)
    scheduler.add_job(decide_intake, "cron", hour=12, minute=30, args=[settings], id="intake", **common)
    scheduler.add_job(
        collect_policies, "cron", day_of_week="fri", hour=13, minute=0, args=[settings], kwargs={"weekly_recheck": True}, id="policies-recheck", **common
    )
    scheduler.add_job(Relay(settings).quietly, "interval", seconds=5, id="relay", **common)
    # 처음 수집 고르기는 오래 걸릴 수 있어(모든 출처 목록) 따로 돌려요. 다 골랐으면 바로 끝나요
    threading.Thread(target=first_intake, args=[settings], daemon=True, name="first-intake").start()
    log.info("스케줄러 시작", extra={"sources": ORDER, "policies": POLICY_ORDER})
    scheduler.start()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="mujuthaek_collector", description="지방 공사 주거 공고 수집 워커")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("run", help="스케줄러로 계속 실행")
    once = commands.add_parser("run-once", help="출처 하나를 지금 한 번 수집")
    once.add_argument("source", choices=ORDER + POLICY_ORDER)
    once.add_argument("--recheck", action="store_true", help="마감 전 공고(정책은 바뀌지 않은 정책)까지 다시 열어 확인")
    every = commands.add_parser("run-all", help="모든 출처를 순서대로 한 번")
    every.add_argument("--recheck", action="store_true")
    commands.add_parser("run-policies", help="정책 API 출처를 순서대로 한 번")
    commands.add_parser("relay", help="아웃박스 이벤트를 한 번 보내기")
    commands.add_parser("cleanup", help="보관 기한이 지난 원본 파일 지우기")
    fixtures = commands.add_parser("save-fixtures", help="테스트용 화면 저장")
    fixtures.add_argument("source", choices=ORDER)
    fixtures.add_argument("--details", type=int, default=3, help="게시판마다 저장할 상세 수")
    commands.add_parser("status", help="최근 수집 회차 보기")
    intake_cmd = commands.add_parser("intake", help="처음 수집 개수 제한: 묶음마다 고른 결과·기다리는 글 보기")
    intake_cmd.add_argument("--decide", action="store_true", help="기다리는(HELD) 글에서 지금 고르기")
    area = commands.add_parser("area-upload", help="생활권·상권 원천 파일을 S3 area/에 올리고 적재 요청(area.source.ready) 보내기")
    area.add_argument("--source", choices=AREA_SOURCES)
    area.add_argument("--data-date", help="원천 기준일 (YYYY-MM-DD)")
    area.add_argument("--file", help="원천 파일 (CSV, 지하철은 엑셀도 돼요, 도로명주소는 원본 .txt)")
    area.add_argument("--scope", help="상가정보는 시도 이름 (강원, 경기, 전남광주 …), 도로명주소는 시도 코드 (11, 36110 …)")
    area.add_argument("--manifest", help="이미 올린 파일 목록 CSV (--skip-upload와 같이)")
    area.add_argument("--skip-upload", action="store_true", help="올리지 않고 S3 sha256 메타데이터만 확인해 적재 요청만 보내기")
    area.add_argument(
        "--resend",
        action="store_true",
        help="이미 보낸 적재 요청도 다시 보내기 (브로커가 메시지를 잃어 빠진 적재가 있을 때. 이미 적재한 파일은 api가 건너뛰어요)",
    )
    args = parser.parse_args(argv)
    if args.command == "area-upload":
        if args.manifest and not args.skip_upload:
            parser.error("--manifest는 이미 올린 파일 목록이라 --skip-upload와 같이 써요")
        if not args.manifest and not (args.source and args.data_date and args.file):
            parser.error("--source, --data-date, --file이 필요해요 (또는 --manifest … --skip-upload)")

    platform_logging.setup("collector")
    settings = Settings.from_env()
    if args.command == "run":
        run_scheduler(settings)
    elif args.command == "run-once":
        run = collect_policy if args.source in POLICY_ORDER else collect
        result = run(args.source, settings, recheck=args.recheck)
        print(f"{result.source_code}: {result.status}, 새 버전 {result.new_count}건")
        for warning in result.warnings:
            print(f"  - {warning}")
        print(f"이벤트 발행: {relay(settings)}건")
    elif args.command == "run-all":
        collect_all(settings, recheck=args.recheck)
        print(f"이벤트 발행: {relay(settings)}건")
    elif args.command == "run-policies":
        collect_policies(settings)
        print(f"이벤트 발행: {relay(settings)}건")
    elif args.command == "relay":
        print(f"이벤트 발행: {relay(settings)}건")
    elif args.command == "cleanup":
        print(f"지운 파일: {cleanup(settings)}개")
    elif args.command == "save-fixtures":
        save_fixtures(args.source, settings, args.details)
    elif args.command == "status":
        print_status(settings)
    elif args.command == "intake":
        print_intake(settings, args.decide)
    elif args.command == "area-upload":
        raise SystemExit(area_upload(args, settings))


if __name__ == "__main__":
    main()
