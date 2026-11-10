"""관리자 「추출 과정 보기」: 작업 기록(extraction_jobs.usage)을 화면용으로 줄입니다.

V2 작업 기록(usage.v2)에는 담당(섹션 에이전트)마다 차례별 도구 호출·결과·검증 메시지와 마지막 초안, 모델 호출마다 토큰·비용이 있어요.
화면은 「누가 무엇을 넣고, 무엇이 거절돼 어떻게 고쳤고, 얼마가 들었나」를 보여 주므로 그에 필요한 것만 남깁니다.
- 공고 원문·추출 값 앞부분(도구 인자·결과는 기록 때 이미 400자까지)은 공개 공고 내용이라 그대로 둡니다. 사용자 정보는 기록에 없습니다.
- 모델의 추론 요약(암호화된 reasoning 묶음)은 화면에 쓸모가 없어 뺍니다.
- 검증 메시지는 차례마다 길어(최대 8,000자) 앞부분만 둡니다.
"""

from __future__ import annotations

import json
from typing import Any

VERIFY_CHARS = 2_000  # 차례마다 보여 줄 검증 메시지 앞부분
TEXT_CHARS = 200
SUMMARY_CHARS = 600  # 담당이 끝낼 때 남긴 요약

# 호출 기록·담당 기록의 이름 → 화면 이름 (모르는 이름은 그대로)
LABELS = {
    "prime": "캐시 데우기",
    "supply_tables": "공급표 열 의미",
    "structure": "구조 (공고·위치·공급)",
    "schedules": "일정 담당",
    "eligibility": "자격 담당",
    "selection": "선정 담당",
    "documents": "서류 담당",
    "resolver": "해결 담당",
    "criteria_table": "기준표 담당",
}


def label(name: str | None) -> str:
    return LABELS.get(name or "", name or "이름 없음")


def trace_view(usage: dict[str, Any] | None) -> dict[str, Any]:
    """작업 기록 → 화면용 요약. V2 기록이 없으면(V1 시절 작업·채팅 모델 없는 실행) engine=V1과 합계만."""
    usage = usage or {}
    v1_totals = usage.get("totals") or {}
    v2 = usage.get("v2") or {}
    calls = [c for c in v2.get("calls") or [] if isinstance(c, dict) and "seconds" in c]
    by_agent = _by_agent(calls)
    v1_cost = float(v1_totals.get("costUsd") or 0)
    return {
        "engine": "V2" if v2 else "V1",
        "totalSeconds": usage.get("totalSeconds"),
        "workers": [{"agent": w, "label": label(w)} for w in v2.get("workers") or []],
        "totals": {
            "costUsd": round(v1_cost + sum(a["costUsd"] for a in by_agent), 6),
            "calls": int(v1_totals.get("calls") or 0) + len(calls),
            "inputTokens": int(v1_totals.get("inputTokens") or 0) + sum(a["inputTokens"] for a in by_agent),
            "cachedTokens": int(v1_totals.get("cachedTokens") or 0) + sum(a["cachedTokens"] for a in by_agent),
            "outputTokens": int(v1_totals.get("outputTokens") or 0) + sum(a["outputTokens"] for a in by_agent),
        },
        # V1 방식 호출(그림 판독·끝 단계 재확인 등): 합계만
        "v1Calls": {"calls": int(v1_totals.get("calls") or 0), "costUsd": round(v1_cost, 6)},
        "byAgent": by_agent,
        # 끝내기 전에 멈춘 담당(호출 상한·예산·모델 오류)과 응답을 받지 못한 시도(데우기·구조)
        "stopped": [
            {"agent": c.get("agent"), "label": label(c.get("agent")), "reason": str(c["stopped"])}
            for c in v2.get("calls") or []
            if isinstance(c, dict) and c.get("stopped")
        ],
        "agents": [_agent(t) for t in v2.get("traces") or [] if isinstance(t, dict)],
    }


def _by_agent(calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """호출 기록을 담당 이름별로(처음 나온 순서) 합칩니다."""
    out: dict[str, dict[str, Any]] = {}
    for c in calls:
        name = str(c.get("agent") or "")
        a = out.setdefault(
            name,
            {
                "agent": name,
                "label": label(name),
                "calls": 0,
                "seconds": 0.0,
                "inputTokens": 0,
                "cachedTokens": 0,
                "outputTokens": 0,
                "costUsd": 0.0,
                "cacheHits": 0,
            },
        )
        a["calls"] += 1
        a["seconds"] += float(c.get("seconds") or 0)
        for key in ("inputTokens", "cachedTokens", "outputTokens"):
            a[key] += int(c.get(key) or 0)
        a["costUsd"] += float(c.get("costUsd") or 0)
        a["cacheHits"] += 1 if c.get("cacheHit") else 0
    for a in out.values():
        a["seconds"] = round(a["seconds"], 3)
        a["costUsd"] = round(a["costUsd"], 6)
    return list(out.values())


def _agent(trace: dict[str, Any]) -> dict[str, Any]:
    turns = [_turn(t) for t in trace.get("turns") or [] if isinstance(t, dict)]
    draft = trace.get("draft") if isinstance(trace.get("draft"), dict) else {}
    out: dict[str, Any] = {
        "agent": trace.get("agent"),
        "label": label(trace.get("agent")),
        "stopped": trace.get("stopped"),
        # 초안의 finished는 담당이 finish로 남긴 한두 문장(끝내지 못했으면 비어 있음)
        "finished": bool(draft.get("finished")),
        "summary": str(draft["finished"])[:SUMMARY_CHARS] if draft.get("finished") else None,
        "items": {section: len(rows) for section, rows in (draft.get("items") or {}).items() if isinstance(rows, list)},
        "coverage": draft.get("coverage") or {},
        "missing": len(draft.get("missing") or []),
        "rejected": [{"item": key, "reasons": reasons} for key, reasons in (draft.get("rejected") or {}).items()],
        "tools": _tool_counts(turns),
        "failedResults": sum(1 for t in turns for r in t["results"] if r["failed"]),
        "verifyRounds": sum(1 for t in turns if t.get("verify")),
        "turns": turns,
    }
    problems = trace.get("problems") or ([trace["problem"]] if trace.get("problem") else [])
    if problems:
        out["problems"] = problems
    resolver = trace.get("resolver")
    if isinstance(resolver, dict):
        out["resolver"] = {
            **{k: resolver.get(k) for k in ("targets", "before", "after", "adopted", "runs")},
            "conversations": [
                {**{k: run.get(k) for k in ("targets", "after", "adopted", "stopped", "refused")}, "turns": [_turn(t) for t in run.get("turns") or []]}
                for run in resolver.get("items") or []
                if isinstance(run, dict)
            ],
        }
    tables = trace.get("tables")
    if isinstance(tables, list):
        out["tables"] = [
            {**{k: t.get(k) for k in ("table", "rows", "groups", "stopped")}, "turns": [_turn(x) for x in t.get("turns") or []]}
            for t in tables
            if isinstance(t, dict)
        ]
    return out


def _turn(turn: dict[str, Any]) -> dict[str, Any]:
    text = turn.get("text") if isinstance(turn.get("text"), str) else ""
    out: dict[str, Any] = {
        "calls": [{"name": c.get("name"), "args": c.get("args")} for c in turn.get("calls") or [] if isinstance(c, dict)],
        "results": [
            {"name": r.get("name"), "result": r.get("result"), "failed": _failed(r.get("result"))} for r in turn.get("results") or [] if isinstance(r, dict)
        ],
    }
    # 모델이 글로 남긴 말만. 추론 묶음(「[{"id": "rs_…", "type": "reasoning", …」)은 JSON 목록으로 기록돼 있어 뺍니다
    if text.strip() and not text.lstrip().startswith("["):
        out["text"] = text[:TEXT_CHARS]
    if turn.get("verify"):
        out["verify"] = str(turn["verify"])[:VERIFY_CHARS]
    return out


def _failed(result: Any) -> bool:
    """도구 결과가 거절·오류인지: 넣기·고치기 결과의 error·errors·failed 칸, 또는 JSON이 아닌 오류 글(도구 오류 미들웨어)."""
    if not isinstance(result, str):
        return False
    try:
        body = json.loads(result)
    except ValueError:
        # 기록이 400자에서 잘려 JSON이 깨진 결과도 있어 남은 글의 칸 이름으로 봅니다. 앞부분만 보면 「added」 목록이 길 때 뒤의
        # 「failed」(일부 거절)를 놓쳤어요. 결과에는 항목 id·오류 문구만 있어 값 속 글자와 헷갈리지 않아요
        return '"error' in result or '"failed": [{' in result or result.startswith(("Error", "오류"))
    if isinstance(body, dict):
        return bool(body.get("error") or body.get("errors") or body.get("failed"))
    return False


def _tool_counts(turns: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for turn in turns:
        for call in turn["calls"]:
            name = str(call.get("name") or "")
            counts[name] = counts.get(name, 0) + 1
    return counts
