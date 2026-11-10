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
