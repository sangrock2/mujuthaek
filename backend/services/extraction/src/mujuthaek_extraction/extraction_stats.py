"""관리자 「추출 비용·품질」 집계 (검수 API GET /stats/extraction?days=, 2026-11-11).

기간: 한국 시간 오늘을 넣어 최근 days일(1~90). 오늘이 11일이고 days=7이면 5일 0시부터예요.

공고 단위(처리 공고)는 원본·버전(rawPostId + version)이에요. 같은 버전을 다시 처리하면 작업이 여러 개라
- 상태는 그 기간의 마지막 작업으로 셉니다(실패 뒤 다시 처리해 게시됐으면 게시). 원본 ID가 없는 작업(형식이 틀린 이벤트)은 작업 하나가 하나예요.
- 비용은 그 버전의 기간 안 작업 비용(cost_usd, 예산 기준 추정: 응답 못 받은 호출은 최악 비용)을 모두 더합니다.
상태 묶음: 자동 게시 COMPLETED · 부분 게시 PARTIAL · 검수로 감 IN_REVIEW·INTAKE_REVIEW·APPROVED · 실패 FAILED·WAITING_SOURCE·INTERRUPTED
  · 그 밖 REJECTED(형식 오류)·UNSUPPORTED(규칙 없는 분야)·SUPERSEDED(더 새 버전이 이미 게시).
  검수 없이 게시 = 자동 게시 + 부분 게시(보류 항목이 검수 목록에 올라도 공고는 이미 게시돼요).
  승인하면 작업 상태가 APPROVED로 바뀌어 원래 상태가 남지 않아요: 확인 표시로 검수 목록에 올랐던 자동·부분 게시 공고도 승인 뒤에는
  「검수로 감」으로 셉니다(검수 없이 게시 비율은 그만큼 낮게 나올 수 있어요).

작업 기록(usage) 집계는 「추출 과정 보기」(trace_view)와 같은 규칙이에요. 기간 안 작업을 최근 것부터 MAX_USAGE_JOBS개까지 봅니다(넘으면 truncated).
- 담당별 비용: V2 호출 기록(usage.v2.calls)의 담당별 비용 + V1 방식 호출(그림 판독·재확인 등, usage.totals) 합계. 비중은 이 합계 대비예요.
- 캐시로 읽은 입력 비율: 캐시 읽기 토큰 ÷ 입력 토큰(입력 토큰에 캐시 읽기가 들어 있어요).
- 멈춤: 담당이 끝내기 전에 멈춘 기록(usage.v2.calls의 stopped, 데우기·구조 시도 포함)을 이유별로: 호출 상한·예산 상한·출력 한도·오류.
- 넣기 거절: 넣기 도구(add_<섹션>) 결과가 거절·오류인 횟수(담당·기준표 담당·해결 담당 대화 모두). 남은 거절은 끝까지 넣지 못한 항목 수.
- 해결 담당: 경고가 남아 해결 담당이 돈 담당 수, 그 결과를 채택한 담당 수, 해결 대화 수.
사용자 정보는 작업 기록에 없어요(공고 원문·추출 값만).
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, timedelta
from typing import Any

from mujuthaek_extraction.trace_view import trace_view

MAX_DAYS = 90
MAX_USAGE_JOBS = 3000  # 작업 기록(usage)을 풀어 볼 최대 작업 수. 넘으면 최근 것만 보고 truncated
TOP_JOBS = 10

AUTO, PARTIAL, REVIEW, FAILED, OTHER = "AUTO", "PARTIAL", "REVIEW", "FAILED", "OTHER"
GROUP_LABELS = {AUTO: "자동 게시", PARTIAL: "부분 게시", REVIEW: "검수로 감", FAILED: "실패", OTHER: "그 밖"}
STATUS_GROUP = {
    "COMPLETED": AUTO,
    "PARTIAL": PARTIAL,
    "IN_REVIEW": REVIEW,
    "INTAKE_REVIEW": REVIEW,
    "APPROVED": REVIEW,
    "FAILED": FAILED,
    "WAITING_SOURCE": FAILED,
    "INTERRUPTED": FAILED,
}

CALL_LIMIT, BUDGET, OUTPUT_LIMIT, ERROR = "CALL_LIMIT", "BUDGET", "OUTPUT_LIMIT", "ERROR"
STOP_LABELS = {CALL_LIMIT: "호출 상한", BUDGET: "예산 상한", OUTPUT_LIMIT: "출력 한도", ERROR: "오류"}


def status_group(status: str | None) -> str:
    return STATUS_GROUP.get(status or "", OTHER)


def stop_kind(reason: str) -> str:
    """멈춘 이유 글(v2/agents/section.py) → 종류. 「모델 호출 상한(N번)」, 「…공고 예산 상한($x)에 닿아…」(BudgetExceeded),
    「출력 한도(N토큰)에서 잘림」, 그 밖은 모델·연결 오류(「APITimeoutError: …」)."""
    if "호출 상한" in reason:
        return CALL_LIMIT
    if "예산 상한" in reason or reason.startswith("BudgetExceeded"):
        return BUDGET
    if "출력 한도" in reason:
        return OUTPUT_LIMIT
    return ERROR


def statuses(rows: Iterable[tuple[str | None, int, float]]) -> dict[str, Any]:
    """[(마지막 작업 상태, 공고 수, 비용)] → 상태 묶음별 공고 수·비율과 원래 상태별 공고 수, 검수 없이 게시 비율."""
    raw: dict[str, int] = {}
    groups = {g: {"group": g, "label": label, "notices": 0, "costUsd": 0.0} for g, label in GROUP_LABELS.items()}
    for status, notices, cost in rows:
        raw[status or "UNKNOWN"] = raw.get(status or "UNKNOWN", 0) + int(notices)
        group = groups[status_group(status)]
        group["notices"] += int(notices)
        group["costUsd"] += float(cost)
    total = sum(raw.values())
    for g in groups.values():
        g["ratio"] = round(g["notices"] / total, 4) if total else None
        g["costUsd"] = round(g["costUsd"], 4)
    published = groups[AUTO]["notices"] + groups[PARTIAL]["notices"]
    return {
        "groups": list(groups.values()),
        "byStatus": dict(sorted(raw.items(), key=lambda kv: -kv[1])),
        "publishedWithoutReview": published,
        "publishedWithoutReviewRatio": round(published / total, 4) if total else None,
    }


def usage_stats(usages: Iterable[Any]) -> dict[str, Any]:
    """작업 기록(usage) 여러 개 → 담당별 비용 비중·캐시 비율·멈춤·넣기 거절·해결 담당 채택. 작업마다 trace_view로 줄인 뒤 더합니다."""
    jobs = v2_jobs = jobs_with_stops = 0
    input_tokens = cached_tokens = output_tokens = 0
    cost = 0.0
    agents: dict[str, dict[str, Any]] = {}
    stops = dict.fromkeys(STOP_LABELS, 0)
    stops_by_agent: dict[str, dict[str, Any]] = {}
    add_rejections = rejected_left = 0
    resolver = {"agents": 0, "adopted": 0, "conversations": 0}
    for usage in usages:
        view = trace_view(usage if isinstance(usage, dict) else None)
        jobs += 1
        v2_jobs += view["engine"] == "V2"
        totals = view["totals"]
        input_tokens += totals["inputTokens"]
        cached_tokens += totals["cachedTokens"]
        output_tokens += totals["outputTokens"]
        cost += totals["costUsd"]
        if view["v1Calls"]["calls"]:
            _add_agent(agents, "v1", "V1 방식 호출(그림 판독·재확인 등)", view["v1Calls"]["calls"], view["v1Calls"]["costUsd"])
        for a in view["byAgent"]:
            _add_agent(agents, a["agent"], a["label"], a["calls"], a["costUsd"])
        jobs_with_stops += bool(view["stopped"])
        for s in view["stopped"]:
            stops[stop_kind(s["reason"])] += 1
            entry = stops_by_agent.setdefault(str(s["agent"] or ""), {"agent": s["agent"], "label": s["label"], "count": 0})
            entry["count"] += 1
        for agent in view["agents"]:
            add_rejections += _add_rejections(agent)
            rejected_left += len(agent["rejected"])
            run = agent.get("resolver")
            if run and run.get("runs"):
                resolver["agents"] += 1
                resolver["adopted"] += bool(run.get("adopted"))
                resolver["conversations"] += int(run.get("runs") or 0)
    by_agent = sorted(agents.values(), key=lambda a: -a["costUsd"])
    for a in by_agent:
        a["share"] = round(a["costUsd"] / cost, 4) if cost else None
        a["costUsd"] = round(a["costUsd"], 6)
    return {
        "jobs": jobs,
        "v2Jobs": v2_jobs,
        "costUsd": round(cost, 6),
        "inputTokens": input_tokens,
        "cachedTokens": cached_tokens,
        "outputTokens": output_tokens,
        "cachedRatio": round(cached_tokens / input_tokens, 4) if input_tokens else None,
        "byAgent": by_agent,
        "stops": {
            "total": sum(stops.values()),
            "jobs": jobs_with_stops,
            "byKind": [{"kind": k, "label": STOP_LABELS[k], "count": n} for k, n in stops.items()],
            "byAgent": sorted(stops_by_agent.values(), key=lambda s: -s["count"]),
        },
        "addRejections": add_rejections,
        "rejectedLeft": rejected_left,
        "resolver": resolver,
    }


def _add_agent(agents: dict[str, dict[str, Any]], key: str, label: str, calls: int, cost: float) -> None:
    a = agents.setdefault(key, {"agent": key, "label": label, "calls": 0, "costUsd": 0.0})
    a["calls"] += calls
    a["costUsd"] += cost


def _add_rejections(agent: dict[str, Any]) -> int:
    """담당 하나의 대화(기준표 담당·해결 담당 대화 포함)에서 넣기(add_…) 결과가 거절·오류인 횟수."""
    turn_lists = [agent["turns"], *(t["turns"] for t in agent.get("tables") or [])]
    turn_lists += [c["turns"] for c in (agent.get("resolver") or {}).get("conversations") or []]
    return sum(1 for turns in turn_lists for turn in turns for r in turn["results"] if r["failed"] and str(r["name"] or "").startswith("add_"))


# ---- DB 읽기 (store.JobStore.extraction_stats가 부름) ----
# 기간 시작: 한국 시간 오늘 0시에서 days-1일 전
_SINCE = "(date_trunc('day', now() at time zone 'Asia/Seoul') - make_interval(days => %(days)s - 1)) at time zone 'Asia/Seoul'"
# 기간 안 작업과 그 공고(원본·버전, 원본 ID가 없으면 작업 ID)
_WINDOW = (
    "with w as (select id, status, cost_usd, created_at,"
    " coalesce(raw_post_id::text || ':' || coalesce(raw_version::text, ''), id::text) as notice"
    f" from extraction_jobs where created_at >= {_SINCE})"
)
_PERIOD_SQL = (
    "select to_char((date_trunc('day', now() at time zone 'Asia/Seoul') - make_interval(days => %(days)s - 1)), 'YYYY-MM-DD'),"
    " to_char(now() at time zone 'Asia/Seoul', 'YYYY-MM-DD')"
)
# 공고마다 마지막 작업 상태와 기간 안 비용 합 → 상태별 공고 수·비용 합·공고당 최대 비용
_NOTICES_SQL = (
    _WINDOW + ", last as (select distinct on (notice) notice, status from w order by notice, created_at desc, id desc),"
    " spent as (select notice, sum(cost_usd) as cost from w group by notice)"
    " select l.status, count(*), coalesce(sum(s.cost), 0), coalesce(max(s.cost), 0) from last l join spent s using (notice) group by l.status"
)
_JOBS_SQL = _WINDOW + " select count(*), coalesce(sum(cost_usd), 0) from w"
_DAILY_SQL = (
    _WINDOW + " select to_char(created_at at time zone 'Asia/Seoul', 'YYYY-MM-DD') as day, count(*), count(distinct notice), coalesce(sum(cost_usd), 0)"
    " from w group by day order by day"
)
_TOP_SQL = (
    "select id, status, cost_usd, created_at, coalesce(list_title, list_source_title), source_code, raw_post_id, raw_version"
    f" from extraction_jobs where created_at >= {_SINCE} and cost_usd > 0 order by cost_usd desc, created_at desc, id limit %(top)s"
)
_USAGE_SQL = f"select usage from extraction_jobs where created_at >= {_SINCE} order by created_at desc, id desc limit %(limit)s"


def collect(conn, days: int, usage_limit: int = MAX_USAGE_JOBS, top: int = TOP_JOBS) -> dict[str, Any]:
    """기간(한국 시간 최근 days일)의 추출 비용·품질 집계. 작업 기록은 서버 커서로 조금씩 읽어 한꺼번에 올리지 않아요."""
    params = {"days": days, "top": top, "limit": usage_limit}
    since, today = conn.execute(_PERIOD_SQL, params).fetchone()
    rows = conn.execute(_NOTICES_SQL, params).fetchall()
    jobs, cost = conn.execute(_JOBS_SQL, params).fetchone()
    daily = {day: (int(j), int(n), float(c)) for day, j, n, c in conn.execute(_DAILY_SQL, params).fetchall()}
    top_rows = conn.execute(_TOP_SQL, params).fetchall()
    with conn.transaction(), conn.cursor(name="extraction_stats_usage") as cur:
        cur.itersize = 50
        cur.execute(_USAGE_SQL, params)
        usage = usage_stats(row[0] for row in cur)
    return assemble(days, since, today, rows, int(jobs), float(cost), daily, top_rows, usage, usage_limit)


def assemble(
    days: int,
    since: str,
    today: str,
    notice_rows: list[tuple[Any, ...]],
    jobs: int,
    cost: float,
    daily: dict[str, tuple[int, int, float]],
    top_rows: list[tuple[Any, ...]],
    usage: dict[str, Any],
    usage_limit: int = MAX_USAGE_JOBS,
) -> dict[str, Any]:
    """SQL 결과와 작업 기록 집계를 화면 응답 하나로. 하루 추이는 작업이 없는 날도 0으로 채워요."""
    notices = sum(int(r[1]) for r in notice_rows)
    first, last = date.fromisoformat(since), date.fromisoformat(today)
    trend = []
    for n in range((last - first).days + 1):
        day = (first + timedelta(days=n)).isoformat()
        j, k, c = daily.get(day, (0, 0, 0.0))
        trend.append({"date": day, "jobs": j, "notices": k, "costUsd": round(c, 4)})
    return {
        "days": days,
        "since": since,
        "until": today,
        "jobs": jobs,
        "notices": notices,
        "costUsd": round(cost, 4),
        "costPerNotice": {
            "avgUsd": round(cost / notices, 4) if notices else None,
            "maxUsd": round(max((float(r[3]) for r in notice_rows), default=0.0), 4) if notices else None,
        },
        "statuses": statuses((r[0], int(r[1]), float(r[2])) for r in notice_rows),
        "daily": trend,
        "topJobs": [
            {
                "jobId": str(job_id),
                "status": status,
                "statusGroup": status_group(status),
                "costUsd": round(float(job_cost), 4),
                "createdAt": created.isoformat() if hasattr(created, "isoformat") else created,
                "title": title,
                "sourceCode": source,
                "rawPostId": str(raw_post_id) if raw_post_id else None,
                "rawVersion": raw_version,
            }
            for job_id, status, job_cost, created, title, source, raw_post_id, raw_version in top_rows
        ],
        "usage": {**usage, "limit": usage_limit, "truncated": jobs > usage["jobs"]},
    }
