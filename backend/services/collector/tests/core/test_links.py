"""사람에게 보여 줄 기관 링크 검사(core/links.py, 2026-11-16 보안 감사 L-4). 네트워크 없음."""

import pytest

from mujuthaek_collector.core.links import MAX_LINK_CHARS, public_link


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("https://www.gov.kr/portal/rcvfvrSvc/dtlEx/000000465790", "https://www.gov.kr/portal/rcvfvrSvc/dtlEx/000000465790"),
        ("  http://youth.incheon.go.kr/apply \n", "http://youth.incheon.go.kr/apply"),
        ("HTTPS://Apply.Example.go.kr/A?b=1#c", "https://Apply.Example.go.kr/A?b=1#c"),  # 계약 패턴 ^https?://에 맞게 scheme만 소문자로
        ("www.youthcenter.go.kr/main", "https://www.youthcenter.go.kr/main"),  # scheme 없이 도메인으로 시작하면 https
        ("global.venture.center/launchpad", "https://global.venture.center/launchpad"),
        ("https://www.gov.kr/공고/1?쪽=2", "https://www.gov.kr/공고/1?쪽=2"),
        ("https://211.45.1.10:8080/apply", "https://211.45.1.10:8080/apply"),  # 공인 IP는 받아요
        ("https://example.go.kr/" + "a" * (MAX_LINK_CHARS - 22), "https://example.go.kr/" + "a" * (MAX_LINK_CHARS - 22)),
    ],
)
def test_public_http_links_are_kept(value, expected):
    assert public_link(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        None,
        123,
        "",
        "   ",
        "-",
        "홈페이지 참조",
        "3.14",
        "1.5배",
        # http(s)가 아닌 주소: React는 javascript:만 막아요(data:·search-ms:·ms-*:·intent:는 그대로 열려요)
        "javascript:alert(1)",
        "JaVaScRiPt:alert(document.cookie)",
        "data:text/html,<script>alert(1)</script>",
        "vbscript:msgbox(1)",
        "search-ms:query=x",
        "ms-settings:privacy",
        "intent://scan/#Intent;scheme=zxing;end",
        "file:///C:/Windows/win.ini",
        "ftp://example.go.kr/a",
        # 호스트가 없거나 「scheme://호스트」 꼴이 아님
        "//evil.example/a",
        "/relative/path",
        "https:/evil.example",
        "https:///evil.example",
        "https://",
        # 사용자 정보·역슬래시(브라우저는 \를 /로 읽어 다른 호스트로 갈 수 있어요)
        "https://user:pw@example.go.kr/",
        "https://@example.go.kr/",
        "https://example.go.kr@evil.example/",
        "https://good.go.kr\\@evil.example/",
        "https://evil.example\\.good.go.kr/",
        # 빈칸·제어 문자·보이지 않는 서식 문자
        "https://exa mple.go.kr/",
        "https://example.go.kr/a\nb",
        "https://example.go.kr/a\x00b",
        "https://example.go.kr/\u202egnp.exe",
        "https://example.go.kr/\u200b",
        "https://example.go.kr/a\u3000b",
        # 사설·루프백 주소와 브라우저가 IP로 읽는 숫자 호스트
        "https://127.0.0.1/admin",
        "http://192.168.0.1/",
        "http://10.0.0.5:8080/",
        "http://[::1]/",
        "http://localhost:8080/",
        "http://api.localhost/",
        "http://2130706433/",
        "http://0x7f.1/",
        "http://1.2.3/",
        # 포트가 숫자가 아니거나 범위를 넘음, 너무 긴 주소
        "https://example.go.kr:99999/",
        "https://example.go.kr:abc/",
        "https://example.go.kr/" + "a" * MAX_LINK_CHARS,
    ],
)
def test_other_values_are_dropped(value):
    assert public_link(value) is None
