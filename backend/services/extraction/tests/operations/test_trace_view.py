"""관리자 「추출 과정 보기」 요약(trace_view)과 검수 API의 /reviews/{id}/trace (DB 없이)."""

import json
from contextlib import contextmanager

from mujuthaek_extraction.review_api import ReviewService
from mujuthaek_extraction.trace_view import VERIFY_CHARS, trace_view


def usage():
    """실제 V2 작업 기록(usage.v2)과 같은 모양의 작은 예."""
    return {
        "format": 1,
        "totalSeconds": 180.5,
        "stages": {},
        "totals": {"calls": 2, "costUsd": 0.004, "inputTokens": 1000, "cachedTokens": 0, "outputTokens": 200},
        "calls": [],
        "v2": {
            "workers": ["structure", "eligibility"],
            "calls": [
                {"agent": "prime", "seconds": 4.9, "inputTokens": 100000, "cachedTokens": 0, "outputTokens": 80, "costUsd": 0.0133, "cacheHit": False},
                {
                    "agent": "eligibility",
                    "seconds": 20.0,
                    "inputTokens": 101000,
                    "cachedTokens": 100000,
                    "outputTokens": 3000,
                    "costUsd": 0.0026,
                    "cacheHit": False,
                },
                {
                    "agent": "eligibility",
                    "seconds": 10.0,
                    "inputTokens": 102000,
                    "cachedTokens": 100000,
                    "outputTokens": 900,
                    "costUsd": 0.0017,
                    "cacheHit": False,
                },
                {"agent": "resolver", "seconds": 5.0, "inputTokens": 101000, "cachedTokens": 100000, "outputTokens": 500, "costUsd": 0.0015, "cacheHit": False},
                {"agent": "structure", "stopped": "ModelError: 시간 초과"},  # 받지 못한 시도 기록(호출 수에 넣지 않음)
            ],
            "traces": [
                {
                    "agent": "eligibility",
                    "stopped": None,
                    "turns": [
                        {
                            "calls": [{"name": "add_eligibility", "args": '{"items": [{"id": "age"}]}'}],
                            "text": '[{"id": "rs_1", "type": "reasoning", "encrypted_content": "gAAA"}]',
                            "results": [
                                {
                                    "name": "add_eligibility",
                                    "result": json.dumps({"failed": [{"id": "age", "errors": ["/rule: 칸이 필요합니다"]}]}, ensure_ascii=False),
                                }
                            ],
                            "verify": "# 검증 결과\n" + "가" * (VERIFY_CHARS + 500),
                        },
                        {
                            "calls": [{"name": "update_item", "args": '{"item": "age"}'}, {"name": "finish", "args": "{}"}],
                            "text": "나이 조건을 고쳤어요.",
                            "results": [{"name": "update_item", "result": '{"ok": true}'}, {"name": "finish", "result": '{"ok": true}'}],
                        },
                    ],
                    "resolver": {
                        "targets": 3,
                        "before": 3,
                        "after": 1,
                        "adopted": 1,
                        "runs": 1,
                        "items": [{"targets": 3, "after": 1, "adopted": True, "stopped": None, "turns": [{"calls": [], "text": "", "results": []}]}],
                    },
                    "draft": {
                        "items": {"eligibility": [{"id": "age"}, {"id": "income"}]},
                        "coverage": {"eligibility": {"status": "EXTRACTED", "reason": None}},
                        "missing": [],
                        "finished": "나이·소득 조건을 넣었어요.",
                        "rejected": {"eligibility/car": ["/rule: 칸이 필요합니다"]},
                    },
                }
            ],
        },
    }


def test_v2_trace_summarizes_agents_tools_rejections_and_costs():
    view = trace_view(usage())
    assert view["engine"] == "V2"
    assert [a["agent"] for a in view["byAgent"]] == ["prime", "eligibility", "resolver"]
    eligibility = view["byAgent"][1]
    assert eligibility["calls"] == 2 and eligibility["label"] == "자격 담당"
    assert eligibility["cachedTokens"] == 200000 and eligibility["costUsd"] == 0.0043
    # V1식 호출(그림 판독·재확인) 합계 + V2 호출
    assert view["totals"]["calls"] == 2 + 4
    assert view["totals"]["costUsd"] == round(0.004 + 0.0133 + 0.0026 + 0.0017 + 0.0015, 6)
    assert view["stopped"] == [{"agent": "structure", "label": "구조 (공고·위치·공급)", "reason": "ModelError: 시간 초과"}]

    agent = view["agents"][0]
    assert agent["tools"] == {"add_eligibility": 1, "update_item": 1, "finish": 1}
    assert agent["failedResults"] == 1 and agent["verifyRounds"] == 1
    assert agent["items"] == {"eligibility": 2} and agent["finished"] is True
    assert agent["summary"] == "나이·소득 조건을 넣었어요."
    assert agent["rejected"] == [{"item": "eligibility/car", "reasons": ["/rule: 칸이 필요합니다"]}]
    first, second = agent["turns"]
    assert "text" not in first  # 추론 묶음은 뺌
    assert second["text"] == "나이 조건을 고쳤어요."
    assert len(first["verify"]) == VERIFY_CHARS
    assert first["results"][0]["failed"] is True and second["results"][0]["failed"] is False
    assert agent["resolver"]["adopted"] == 1 and agent["resolver"]["conversations"][0]["adopted"] is True


def test_result_cut_at_400_chars_is_still_judged_by_its_fields():
    view = trace_view(usage())
    long_added = '{"added": [' + ", ".join(f'"elig-{i}"' for i in range(30))
    turn = {
        "calls": [],
        "results": [
            {"name": "add_eligibility", "result": '{"error": "형식이 틀렸어요: ' + "가" * 400},
            # 2026-11-10 jbdc 실제 기록: 넣은 id 목록이 길어 「failed」(일부 거절)가 120자 뒤에 있었음
            {"name": "add_eligibility", "result": long_added + '], "failed": [{"id": "elig-age", "errors": ["/rule'},
            {"name": "add_eligibility", "result": long_added},
        ],
    }
    data = usage()
    data["v2"]["traces"][0]["turns"] = [turn]
    results = trace_view(data)["agents"][0]["turns"][0]["results"]
    assert [r["failed"] for r in results] == [True, True, False]
    assert view["agents"][0]["turns"][1]["results"][1]["failed"] is False


def test_v1_job_without_v2_record_gives_totals_only():
    view = trace_view({"totalSeconds": 60, "totals": {"calls": 5, "costUsd": 0.03, "inputTokens": 9000, "cachedTokens": 0, "outputTokens": 800}})
    assert view["engine"] == "V1" and view["agents"] == [] and view["byAgent"] == []
    assert view["totals"]["calls"] == 5 and view["totals"]["costUsd"] == 0.03
    assert trace_view(None)["engine"] == "V1"


class FakeStore:
    def __init__(self, job):
        self.job = job

    def job_usage(self, job_id):
        return dict(self.job) if self.job else None


def service_with(store):
    @contextmanager
    def session():
        yield store

    return ReviewService(session, lambda *a: {})


def test_review_service_trace_returns_job_and_summary_or_404():
    job = {"jobId": "j-1", "jobStatus": "PARTIAL", "rawPostId": "p-1", "modelUsed": "gpt-6-luna", "costUsd": 0.025, "usage": usage()}
    status, body = service_with(FakeStore(job)).trace("j-1")
    assert status == 200 and body["jobId"] == "j-1" and body["engine"] == "V2" and "usage" not in body
    assert service_with(FakeStore(None)).trace("j-2")[0] == 404
    status, body = service_with(FakeStore({**job, "usage": None})).trace("j-1")
    assert status == 200 and body["engine"] == "V1"
