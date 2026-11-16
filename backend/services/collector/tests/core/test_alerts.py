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


def test_crawled_titles_in_warnings_reach_slack_inert(monkeypatch):
    # 2026-11-16 보안 감사 L-22: 최근 경고 3개(크롤링한 제목·주소)를 그대로 코드 블록에 넣어 <!channel>·링크·코드 블록 탈출이 됐어요
    from mujuthaek_platform.slack import QuietAlerts, SlackNotifier

    texts: list[str] = []

    class Fake(SlackNotifier):
        def send(self, text: str) -> bool:
            texts.append(text)
            return True

    monkeypatch.setattr(main, "_alerts", QuietAlerts(Fake("https://hooks.example.invalid/x"), "collector", environment="prod"))
    monkeypatch.setattr(main, "_failure_runs", {})
    warnings = ["[P1] ```\n<!channel> 긴급 공지 — 상세를 읽지 못했어요", "[P2] <https://evil.example|여기를 누르세요> & <@U123> — 저장하지 못했어요"]
    for _ in range(3):
        main.alert_on_trouble("lh", result("FAILED", warnings))
    [text] = texts
    assert "<!channel>" not in text and "<https://evil.example|" not in text and "<@U123>" not in text
    assert "&lt;!channel&gt;" in text and "&lt;https://evil.example|여기를 누르세요&gt; &amp; &lt;@U123&gt;" in text
    assert text.count("```") == 2 and text.endswith("```")  # 경고 안의 백틱이 코드 블록을 닫지 못해요
