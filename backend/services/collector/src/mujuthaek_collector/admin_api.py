"""관리자 수집 현황 API (:8093, 2026-10-25). api 서버가 대신 불러 관리자 화면 「수집 현황」에 보여 줘요.

  GET  /sources                출처별 상태: 켜짐 여부, 마지막 회차·마지막 성공, 최근 회차 10개, 연속 0건·연속 실패, 누적 수집 수
  POST /sources/{code}/pause   멈춤 (sources.enabled = false). 스케줄러는 켜진 출처만 돌아요(enabled_sources)
  POST /sources/{code}/resume  다시 켜기
  POST /sources/{code}/run     지금 한 번 수집 (202, 뒤에서 돌아요). 다른 수집이 돌고 있거나(스케줄러와 같은 잠금) 그 출처가 수집 중·멈춤이면 409

인증: COLLECTOR_ADMIN_TOKEN이 있으면 'Authorization: Bearer <토큰>'이 필요해요. 없으면 같은 컴퓨터(127.0.0.1·::1)에서 온 요청만 받아요.
오류 글(crawl_runs.error)은 앞부분만 내보내요(키는 수집 단계에서 이미 가려요).
「지금 다시 수집」은 스케줄러가 쓰는 수집 함수와 출처 잠금(SourceLocks)을 그대로 받아 써요(Runner). 그 출처를 수집하는 동안 그 출처의 정해진 차례만 건너뛰어요.
"""

from __future__ import annotations

import hmac
import json
import logging
import os
import re
import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

log = logging.getLogger(__name__)

ADMIN_PORT = int(os.getenv("COLLECTOR_ADMIN_PORT", "8093"))
LOOPBACK = {"127.0.0.1", "::1", "::ffff:127.0.0.1"}
ACTION_PATH = re.compile(r"^/sources/([a-z0-9_-]{1,40})/(pause|resume|run)$")
RUNNING_WITHIN = timedelta(hours=2)  # 이보다 오래된 RUNNING 회차는 비정상 종료로 보고 무시해요
RECENT_RUNS = 10
ERROR_CHARS = 300
# 켜진 출처가 이 시간 넘게 성공한 회차가 없으면 「지연」 (평일 매시간·하루 1회 출처가 섞여 있어 넉넉히)
LATE_AFTER = timedelta(hours=26)


def _iso(value: Any) -> str | None:
    return value.isoformat() if isinstance(value, datetime) else None


def sources_status(conn: Any, now: datetime | None = None) -> dict[str, Any]:
    """출처별 상태와 요약(정상·지연·실패·멈춤 수)."""
    now = now or datetime.now(UTC)
    sources = conn.execute("select code, name, enabled from sources order by code").fetchall()
    runs = conn.execute(
        "select source_code, started_at, finished_at, status, new_count, left(coalesce(error, ''), %s)"
        " from (select *, row_number() over (partition by source_code order by started_at desc) as n from crawl_runs) r"
        " where n <= %s order by source_code, started_at desc",
        (ERROR_CHARS, RECENT_RUNS),
    ).fetchall()
    last_success = dict(conn.execute("select source_code, max(finished_at) from crawl_runs where status = 'SUCCESS' group by source_code").fetchall())
    totals: dict[str, int] = {}
    for table in ("raw_posts", "raw_policies"):
        for code, count in conn.execute(f"select source_code, count(*) from {table} group by source_code").fetchall():
            totals[code] = totals.get(code, 0) + count
    by_source: dict[str, list[dict[str, Any]]] = {}
    for code, started, finished, status, new_count, error in runs:
        by_source.setdefault(code, []).append(
            {"startedAt": _iso(started), "finishedAt": _iso(finished), "status": status, "newCount": new_count, "error": error or None}
        )
    rows = []
    summary = {"ok": 0, "late": 0, "fail": 0, "paused": 0}
    for code, name, enabled in sources:
        recent = by_source.get(code, [])
        finished = [r for r in recent if r["status"] != "RUNNING"]
        consecutive_empty = 0
        for run in finished:
            if run["status"] != "SUCCESS" or run["newCount"]:
                break
            consecutive_empty += 1
        consecutive_failures = 0
        for run in finished:
            if run["status"] not in ("FAILED", "BLOCKED"):
                break
            consecutive_failures += 1
        success = last_success.get(code)
        if not enabled:
            state = "paused"
        elif consecutive_failures:
            state = "fail"
        elif success is None or now - success > LATE_AFTER:
            state = "late"
        else:
            state = "ok"
        summary[state] += 1
        rows.append(
            {
                "code": code,
                "name": name,
                "enabled": enabled,
                "state": state,
                "lastRun": recent[0] if recent else None,
                "lastSuccessAt": _iso(success),
                "consecutiveEmpty": consecutive_empty,
                "consecutiveFailures": consecutive_failures,
                "totalCollected": totals.get(code, 0),
                "recentRuns": recent,
            }
        )
    return {"asOf": now.isoformat(), "summary": summary, "sources": rows}


def set_enabled(conn: Any, code: str, enabled: bool) -> bool:
    """출처를 켜거나 꺼요. 없는 출처면 False."""
    cur = conn.execute("update sources set enabled = %s where code = %s", (enabled, code))
    return cur.rowcount == 1


class Runner:
    """출처 하나를 지금 한 번 수집해요. 스케줄러와 같은 출처 잠금(SourceLocks)·수집 함수를 받아요(__main__.run_scheduler에서 만듦).
    다른 출처가 돌고 있어도 이 출처만 비어 있으면 바로 시작해요."""

    def __init__(self, locks: Any, collect: Callable[..., Any], collect_policy: Callable[..., Any], policy_codes: list[str], settings: Any):
        self.locks = locks
        self.collect = collect
        self.collect_policy = collect_policy
        self.policy_codes = set(policy_codes)
        self.settings = settings

    def start(self, conn: Any, code: str, now: datetime | None = None) -> tuple[int, Any]:
        row = conn.execute("select enabled from sources where code = %s", (code,)).fetchone()
        if row is None:
            return 404, {"error": "없는 출처입니다."}
        if not row[0]:
            return 409, {"error": "멈춘 출처예요. 다시 켠 뒤 수집하세요."}
        now = now or datetime.now(UTC)
        running = conn.execute(
            "select 1 from crawl_runs where source_code = %s and status = 'RUNNING' and started_at > %s limit 1", (code, now - RUNNING_WITHIN)
        ).fetchone()
        if running:
            return 409, {"error": "이 출처는 지금 수집 중이에요."}
        if not self.locks.acquire(code):
            return 409, {"error": "이 출처는 지금 수집 중이에요."}
        run = self.collect_policy if code in self.policy_codes else self.collect

        def work() -> None:
            try:
                run(code, self.settings)
            except Exception:  # noqa: BLE001 — 실패는 crawl_runs와 로그에 남아요
                log.exception("관리자 요청 수집 실패", extra={"source": code})
            finally:
                self.locks.release(code)

        threading.Thread(target=work, daemon=True, name=f"admin-run-{code}").start()
        log.info("관리자 요청으로 수집 시작", extra={"source": code})
        return 202, {"code": code, "started": True}


def handler_for(connect: Callable[[], Any], token: str | None, runner: Runner | None = None) -> type[BaseHTTPRequestHandler]:
    """connect: 요청마다 DB 연결을 여는 함수(닫는 건 여기서). token: 있으면 Bearer 인증."""

    class Handler(BaseHTTPRequestHandler):
        def _allowed(self) -> bool:
            if token:
                given = self.headers.get("Authorization") or ""
                return hmac.compare_digest(given.encode(), f"Bearer {token}".encode())
            return self.client_address[0] in LOOPBACK

        def _send(self, status: int, body: Any) -> None:
            data = json.dumps(body, ensure_ascii=False, default=str).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _with_conn(self, work: Callable[[Any], tuple[int, Any]]) -> None:
            try:
                conn = connect()
            except Exception:  # noqa: BLE001 — DB에 못 붙으면 503으로 알려요(주소·비밀번호는 남기지 않음)
                log.warning("수집 현황 API: DB에 연결하지 못했어요")
                return self._send(503, {"error": "수집 DB에 연결하지 못했어요."})
            try:
                self._send(*work(conn))
            finally:
                conn.close()

        def do_GET(self) -> None:  # noqa: N802
            if not self._allowed():
                return self._send(401, {"error": "인증이 필요합니다."})
            if urlparse(self.path).path != "/sources":
                return self._send(404, {"error": "없는 주소입니다."})
            self._with_conn(lambda conn: (200, sources_status(conn)))

        def do_POST(self) -> None:  # noqa: N802
            if not self._allowed():
                return self._send(401, {"error": "인증이 필요합니다."})
            match = ACTION_PATH.match(urlparse(self.path).path)
            if not match:
                return self._send(404, {"error": "없는 주소입니다."})
            code, action = match[1], match[2]

            def work(conn: Any) -> tuple[int, Any]:
                if action == "run":
                    if runner is None:
                        return 501, {"error": "지금 수집은 스케줄러와 함께 띄웠을 때만 돼요."}
                    return runner.start(conn, code)
                if not set_enabled(conn, code, action == "resume"):
                    return 404, {"error": "없는 출처입니다."}
                log.info("수집 출처 켜기·끄기", extra={"source": code, "action": action})
                return 200, {"code": code, "enabled": action == "resume"}

            self._with_conn(work)

        def log_message(self, *_: Any) -> None:
            return

    return Handler


def serve(db_url: str, runner: Runner | None = None) -> ThreadingHTTPServer:
    """스케줄러와 같이 뒤에서 도는 관리자 API를 시작해요."""
    from mujuthaek_collector.core.storage import PostgresStore

    def connect() -> Any:
        return PostgresStore(db_url).conn

    token = os.getenv("COLLECTOR_ADMIN_TOKEN") or None
    host = os.getenv("COLLECTOR_ADMIN_HOST", "0.0.0.0")
    if not token:
        log.warning("수집 현황 API 토큰(COLLECTOR_ADMIN_TOKEN)이 없어 같은 컴퓨터에서 온 요청만 받아요")
    server = ThreadingHTTPServer((host, ADMIN_PORT), handler_for(connect, token, runner))
    threading.Thread(target=server.serve_forever, daemon=True, name="collector-admin-api").start()
    return server
