"""공통 슬랙 알리미(slack.py). urlopen을 가짜로 바꿔 네트워크 없이 봐요."""

import json
import logging
import urllib.error

import pytest

from mujuthaek_platform import slack
from mujuthaek_platform.slack import SlackError, SlackNotifier, read_env_value

URL = "https://hooks.example.invalid/T/B/secretToken"


class FakeResponse:
    def __init__(self, status):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_send_posts_json_text_with_short_timeout(monkeypatch):
    sent = []

    def fake_urlopen(request, timeout):
        sent.append(
            (request.full_url, request.get_method(), json.loads(request.data), request.headers["Content-type"], timeout)
        )
        return FakeResponse(200)

    monkeypatch.setattr(slack.urllib.request, "urlopen", fake_urlopen)
    assert SlackNotifier(URL).send("안녕") is True
    assert sent == [(URL, "POST", {"text": "안녕"}, "application/json", 5.0)]


@pytest.mark.parametrize(
    "error",
    [
        urllib.error.URLError("연결 거부"),
        TimeoutError("시간 초과"),
        urllib.error.HTTPError(URL, 404, "no_service " + URL, {}, None),
    ],
)
def test_failures_raise_slack_error_without_the_webhook_address(monkeypatch, error):
    def broken(request, timeout):
        raise error

    monkeypatch.setattr(slack.urllib.request, "urlopen", broken)
    with pytest.raises(SlackError) as raised:
        SlackNotifier(URL).send("x")
    assert "secretToken" not in str(raised.value) and raised.value.__cause__ is None
    assert raised.value.__suppress_context__  # 원래 예외(주소가 들어 있을 수 있음)를 이어 붙이지 않아요


def test_non_2xx_status_raises(monkeypatch):
    monkeypatch.setattr(slack.urllib.request, "urlopen", lambda request, timeout: FakeResponse(500))
    with pytest.raises(SlackError, match="500"):
        SlackNotifier(URL).send("x")


def test_without_url_send_is_a_no_op_with_one_warning(monkeypatch, caplog):
    def must_not_call(request, timeout):
        raise AssertionError("주소가 없으면 보내지 않아야 해요")

    monkeypatch.setattr(slack.urllib.request, "urlopen", must_not_call)
    notifier = SlackNotifier(None, env_name="SLACK_WEBHOOK_URL")
    with caplog.at_level(logging.WARNING, logger="mujuthaek_platform.slack"):
        assert notifier.send("a") is False and notifier.send("b") is False
    assert not notifier.enabled
    assert len(caplog.records) == 1 and "SLACK_WEBHOOK_URL" in caplog.records[0].getMessage()


def test_repr_hides_the_url():
    assert "secretToken" not in repr(SlackNotifier(URL)) and "hooks" not in repr(SlackNotifier(URL))


def test_from_env_reads_env_then_env_file_in_name_order(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text('OTHER=1\nexport SERVICE_SLACK="https://hooks.example.invalid/file"\n', encoding="utf-8")
    monkeypatch.delenv("SERVICE_SLACK", raising=False)
    monkeypatch.delenv("COMMON_SLACK", raising=False)
    assert read_env_value(("SERVICE_SLACK", "COMMON_SLACK"), env_file) == "https://hooks.example.invalid/file"
    monkeypatch.setenv("SERVICE_SLACK", "https://hooks.example.invalid/env")
    assert read_env_value(("SERVICE_SLACK", "COMMON_SLACK"), env_file).endswith("/env")  # 환경 변수가 파일보다 먼저
    monkeypatch.setenv("SERVICE_SLACK", "")
    monkeypatch.setenv("COMMON_SLACK", "https://hooks.example.invalid/common")
    assert read_env_value(("SERVICE_SLACK", "COMMON_SLACK"), tmp_path / "missing.env").endswith("/common")
    assert read_env_value("NOPE_SLACK", tmp_path / "missing.env") is None

    notifier = SlackNotifier.from_env(("SERVICE_SLACK", "COMMON_SLACK"), env_file=env_file, timeout=2)
    assert notifier.enabled and notifier.timeout == 2  # 빈 환경 변수는 없는 것으로 보고 파일 값을 써요
    monkeypatch.delenv("COMMON_SLACK")
    assert not SlackNotifier.from_env("COMMON_SLACK").enabled


def test_quiet_alerts_send_once_per_window_and_count_the_rest():
    from mujuthaek_platform.slack import QuietAlerts, SlackNotifier

    sent: list[str] = []

    class Fake(SlackNotifier):
        def send(self, text: str) -> bool:
            sent.append(text)
            return True

    now = [0.0]
    alerts = QuietAlerts(Fake("https://example.invalid/hook"), "extraction", environment="prod", clock=lambda: now[0])

    assert alerts.send("dlq:policy", "정책 메시지를 실패 큐로 보냈어요", "AI_FAILED")
    assert not alerts.send("dlq:policy", "정책 메시지를 실패 큐로 보냈어요")
    assert not alerts.send("dlq:policy", "정책 메시지를 실패 큐로 보냈어요")
    assert alerts.send("dlq:notice", "다른 종류")
    now[0] = 600.0
    assert alerts.send("dlq:policy", "정책 메시지를 실패 큐로 보냈어요")

    assert sent[0] == "[prod extraction] 정책 메시지를 실패 큐로 보냈어요\n```AI_FAILED```"
    assert sent[2] == "[prod extraction] 정책 메시지를 실패 큐로 보냈어요 (지난 알림 뒤 같은 일 2번 더)"


def test_quiet_alerts_swallow_send_failures():
    from mujuthaek_platform.slack import QuietAlerts, SlackError, SlackNotifier

    class Broken(SlackNotifier):
        def send(self, text: str) -> bool:
            raise SlackError("슬랙 응답 500")

    assert not QuietAlerts(Broken("https://example.invalid/hook"), "collector").send("k", "t")


# ── 바깥 글 이스케이프 (2026-11-16 보안 감사 L-22) ─────────────────────
def test_escape_text_makes_mentions_links_and_code_fences_inert():
    from mujuthaek_platform.slack import BACKTICK_STANDIN, escape_text

    mentions = "&lt;!channel&gt; &lt;!here|here&gt; &lt;@U123&gt; &lt;#C1&gt;"
    assert escape_text("<!channel> <!here|here> <@U123> <#C1>") == mentions
    assert escape_text("<https://evil.example|여기를 누르세요>") == "&lt;https://evil.example|여기를 누르세요&gt;"
    assert escape_text("a & b &amp; c") == "a &amp; b &amp;amp; c"  # 엔티티처럼 보이는 글도 글자 그대로 보이게
    tick = BACKTICK_STANDIN
    assert escape_text("```\n*굵게* `코드`") == f"{tick * 3}\n*굵게* {tick}코드{tick}"
    assert escape_text("인천 청년 월세 지원 (2026)") == "인천 청년 월세 지원 (2026)"  # 보통 글은 그대로


def test_escape_text_redacts_secrets_like_the_logs(monkeypatch):
    from mujuthaek_platform.slack import escape_text

    monkeypatch.setenv("DATA_GO_KR_SERVICE_KEY", "example-private-key+/=123")
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.example.invalid/T000/B000/secretToken")
    text = escape_text(
        "요청 실패 serviceKey=example-private-key%2B%2F%3D123 · 웹훅 https://hooks.example.invalid/T000/B000/secretToken"
    )
    assert "example-private-key" not in text and "secretToken" not in text and text.count("[REDACTED]") == 2


def test_quiet_alerts_escape_title_and_detail_and_keep_the_code_block_closed(monkeypatch):
    from mujuthaek_platform.slack import QuietAlerts, SlackNotifier

    sent: list[str] = []

    class Fake(SlackNotifier):
        def send(self, text: str) -> bool:
            sent.append(text)
            return True

    secret = "example-private-key+/=123"
    monkeypatch.setenv("DATA_GO_KR_SERVICE_KEY", secret)
    alerts = QuietAlerts(Fake("https://example.invalid/hook"), "collector", environment="prod")
    # 크롤링한 제목이 코드 블록을 닫고 채널 전체 호출·링크를 넣으려 함.
    # 비밀 값은 내용 상한(2,000자) 경계에 걸쳐 있어요(1991~2016번째 글자): 잘린 앞부분도 남지 않아야 해요
    head = "[P1] ```\n<!channel> <https://evil.example|여기> & 제목\n"
    detail = head + "가" * (1991 - len(head)) + secret
    assert alerts.send("source.failed:lh", "lh <!here> 수집 실패", detail)
    [text] = sent
    assert text.startswith("[prod collector] lh &lt;!here&gt; 수집 실패\n```")
    assert "<!" not in text and "<https://" not in text
    assert "&lt;!channel&gt; &lt;https://evil.example|여기&gt; &amp; 제목" in text
    assert text.count("```") == 2 and text.endswith("```")
    assert secret[:8] not in text  # 가린 뒤 잘라요(자른 뒤 가리면 「example-」가 남아요)
