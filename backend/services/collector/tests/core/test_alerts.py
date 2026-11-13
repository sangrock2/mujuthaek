"""수집기 운영 알림: 연속 실패 3번째에 한 번, 구조 변경 의심 경고."""

from mujuthaek_collector import __main__ as main
from mujuthaek_collector.pipeline import RunResult


class Recorder:
    def __init__(self):
        self.sent: list[tuple[str, str]] = []

    def send(self, kind: str, title: str, detail: str | None = None) -> bool:
        self.sent.append((kind, title))
        return True


def result(status: str, warnings: list[str] | None = None) -> RunResult:
    r = RunResult("lh")
    r.status = status
    r.warnings = warnings or []
    return r


def test_third_failure_in_a_row_is_alerted_once(monkeypatch):
    rec = Recorder()
    monkeypatch.setattr(main, "_alerts", rec)
    monkeypatch.setattr(main, "_failure_runs", {})

    for _ in range(4):
        main.alert_on_trouble("lh", result("FAILED", ["예상 못한 오류: TimeoutError"]))
    assert rec.sent == [("source.failed:lh", "lh 수집이 3번 연달아 실패했어요")]

    main.alert_on_trouble("lh", result("OK"))
    assert main._failure_runs["lh"] == 0


def test_structure_change_warning_is_alerted(monkeypatch):
    rec = Recorder()
    monkeypatch.setattr(main, "_alerts", rec)
    monkeypatch.setattr(main, "_failure_runs", {})

    main.alert_on_trouble("lh", result("OK", ["[임대] 목록이 비어 있어요 (3회 연속) — 사이트 구조 변경 의심"]))
    assert rec.sent == [("source.structure:lh", "lh 사이트 구조가 바뀐 것 같아요")]
