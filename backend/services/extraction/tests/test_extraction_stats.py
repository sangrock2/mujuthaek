"""관리자 「추출 비용·품질」 집계(extraction_stats)와 검수 API의 /stats/extraction (DB 없이)."""

import json
from contextlib import contextmanager
from datetime import UTC, datetime

from test_trace_view import usage

from mujuthaek_extraction.extraction_stats import assemble, statuses, stop_kind, usage_stats
from mujuthaek_extraction.review_api import ReviewService


def stopped_usage():
    """호출 상한·예산·오류로 멈춘 담당과 기준표 담당·해결 담당 대화의 넣기 거절이 있는 V2 기록."""
    data = usage()
    v2 = data["v2"]
    v2["calls"] += [
        {"agent": "eligibility", "stopped": "모델 호출 상한(16번)"},
        {"agent": "documents", "stopped": "documents: 공고 예산 상한($0.30)에 닿아 부르지 않았습니다"},
        {"agent": "prime", "stopped": "BudgetExceeded: prime: 공고 예산 상한($0.30)에 닿아 부르지 않았습니다"},
        {"agent": "selection", "stopped": "출력 한도(16000토큰)에서 잘림"},
    ]
    failed_add = {"name": "add_eligibility", "result": json.dumps({"failed": [{"id": "x", "errors": ["e"]}]})}
    trace = v2["traces"][0]
    trace["tables"] = [{"table": "t1", "rows": "1~3", "groups": [], "stopped": None, "turns": [{"calls": [], "results": [failed_add]}]}]
    trace["resolver"]["items"][0]["turns"] = [{"calls": [], "results": [failed_add, {"name": "update_item", "result": '{"error": "x"}'}]}]
    return data


def test_stop_reasons_are_grouped_by_kind():
    assert stop_kind("모델 호출 상한(16번)") == "CALL_LIMIT"
    assert stop_kind("documents: 공고 예산 상한($0.30)에 닿아 부르지 않았습니다") == "BUDGET"
    assert stop_kind("BudgetExceeded: x") == "BUDGET"
    assert stop_kind("출력 한도(16000토큰)에서 잘림") == "OUTPUT_LIMIT"
    assert stop_kind("APITimeoutError: Request timed out.") == "ERROR"
    assert stop_kind("ModelError: 시간 초과") == "ERROR"


def test_usage_stats_sums_agents_cache_stops_rejections_and_resolver():
    v1_only = {"totals": {"calls": 3, "costUsd": 0.01, "inputTokens": 5000, "cachedTokens": 1000, "outputTokens": 300}}
    stats = usage_stats([usage(), stopped_usage(), v1_only, None])
    assert stats["jobs"] == 4 and stats["v2Jobs"] == 2

    # 비용: V2 기록 두 개(0.004 + 0.0191씩) + V1만 있는 작업 0.01
    assert stats["costUsd"] == round(2 * (0.004 + 0.0133 + 0.0026 + 0.0017 + 0.0015) + 0.01, 6)
    by_agent = {a["agent"]: a for a in stats["byAgent"]}
    assert by_agent["prime"]["costUsd"] == round(2 * 0.0133, 6) and by_agent["prime"]["calls"] == 2
    assert by_agent["eligibility"]["calls"] == 4 and by_agent["v1"]["calls"] == 2 * 2 + 3
    assert stats["byAgent"][0]["agent"] == "prime"  # 비용이 큰 순
    assert abs(sum(a["share"] for a in stats["byAgent"]) - 1) < 0.001

    # 캐시: 입력 토큰에 캐시 읽기가 들어 있음
    assert stats["inputTokens"] == 2 * (1000 + 100000 + 101000 + 102000 + 101000) + 5000
    assert stats["cachedTokens"] == 2 * 300000 + 1000
    assert stats["cachedRatio"] == round(stats["cachedTokens"] / stats["inputTokens"], 4)

    stops = stats["stops"]
    # 구조 시간 초과(두 기록 모두) + 호출 상한·예산 2·출력 한도
    assert {s["kind"]: s["count"] for s in stops["byKind"]} == {"CALL_LIMIT": 1, "BUDGET": 2, "OUTPUT_LIMIT": 1, "ERROR": 2}
    assert stops["total"] == 6 and stops["jobs"] == 2
    assert stops["byAgent"][0] == {"agent": "structure", "label": "구조 (공고·위치·공급)", "count": 2}

    # 넣기 거절: 담당 대화 1번씩 + 기준표 담당 1 + 해결 담당 대화 1 (고치기 오류는 넣기가 아님)
    assert stats["addRejections"] == 1 + 1 + 2
    assert stats["rejectedLeft"] == 2
    assert stats["resolver"] == {"agents": 2, "adopted": 2, "conversations": 2}


def test_usage_stats_without_jobs_has_no_ratios():
    stats = usage_stats([])
    assert stats["jobs"] == 0 and stats["cachedRatio"] is None and stats["byAgent"] == []
    assert stats["stops"]["total"] == 0


def test_statuses_group_final_states_and_published_without_review_ratio():
    result = statuses(
        [
            ("COMPLETED", 6, 0.3),
            ("PARTIAL", 2, 0.2),
            ("IN_REVIEW", 1, 0.1),
            ("APPROVED", 1, 0.05),
            ("INTAKE_REVIEW", 1, 0.0),
            ("FAILED", 1, 0.02),
            ("WAITING_SOURCE", 1, 0.0),
            ("UNSUPPORTED", 1, 0.0),
        ]
    )
    groups = {g["group"]: g for g in result["groups"]}
    assert groups["AUTO"]["notices"] == 6 and groups["PARTIAL"]["notices"] == 2
    assert groups["REVIEW"]["notices"] == 3 and groups["FAILED"]["notices"] == 2 and groups["OTHER"]["notices"] == 1
    assert groups["AUTO"]["ratio"] == round(6 / 14, 4)
    assert result["publishedWithoutReview"] == 8 and result["publishedWithoutReviewRatio"] == round(8 / 14, 4)
    assert list(result["byStatus"])[0] == "COMPLETED"
    empty = statuses([])
    assert empty["publishedWithoutReviewRatio"] is None and all(g["ratio"] is None for g in empty["groups"])


def test_assemble_fills_days_without_jobs_and_marks_truncated_usage():
    created = datetime(2026, 11, 10, 3, 0, tzinfo=UTC)
    body = assemble(
        3,
        "2026-11-09",
        "2026-11-11",
        [("COMPLETED", 2, 0.05, 0.04), ("FAILED", 1, 0.01, 0.01)],
        4,
        0.06,
        {"2026-11-10": (4, 3, 0.06)},
        [("j-1", "COMPLETED", 0.04, created, "행복주택 공고", "LH", "p-1", 2)],
        {"jobs": 2},
        usage_limit=2,
    )
    assert [d["date"] for d in body["daily"]] == ["2026-11-09", "2026-11-10", "2026-11-11"]
    assert body["daily"][0] == {"date": "2026-11-09", "jobs": 0, "notices": 0, "costUsd": 0.0}
    assert body["daily"][1]["jobs"] == 4
    assert body["notices"] == 3 and body["jobs"] == 4
    assert body["costPerNotice"] == {"avgUsd": 0.02, "maxUsd": 0.04}
    top = body["topJobs"][0]
    assert top["jobId"] == "j-1" and top["statusGroup"] == "AUTO" and top["createdAt"].startswith("2026-11-10T03:00")
    assert body["usage"]["truncated"] is True and body["usage"]["limit"] == 2
    none = assemble(7, "2026-11-05", "2026-11-11", [], 0, 0.0, {}, [], {"jobs": 0})
    assert none["costPerNotice"] == {"avgUsd": None, "maxUsd": None} and len(none["daily"]) == 7
    assert none["usage"]["truncated"] is False


class FakeStore:
    def __init__(self):
        self.days = None

    def extraction_stats(self, days):
        self.days = days
        return {"days": days}


def test_review_service_checks_days_range():
    store = FakeStore()

    @contextmanager
    def session():
        yield store

    service = ReviewService(session, lambda *a: {})
    assert service.extraction_stats(None) == (200, {"days": 30})
    assert service.extraction_stats("7") == (200, {"days": 7}) and store.days == 7
    for bad in ("0", "91", "x", "-1"):
        assert service.extraction_stats(bad)[0] == 400
