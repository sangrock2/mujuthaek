import logging
from urllib.parse import quote

from mujuthaek_platform.logging import JsonFormatter


def test_api_key_in_request_url_extra_and_exception_is_not_logged(monkeypatch):
    secret = "example-private-key+/=123"
    monkeypatch.setenv("DATA_GO_KR_SERVICE_KEY", secret)
    record = logging.LogRecord(
        "collector",
        logging.ERROR,
        __file__,
        1,
        "request failed: %s",
        ("https://example.test/?serviceKey=" + quote(secret, safe=""),),
        None,
    )
    record.details = {"echo": secret}
    formatted = JsonFormatter("collector").format(record)
    assert secret not in formatted and quote(secret, safe="") not in formatted
    assert "[REDACTED]" in formatted and "request failed" in formatted
    assert record.details["echo"] == secret
