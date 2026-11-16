"""사람에게 보여 줄 기관 링크(정책 원문·신청 주소) 검사 (2026-11-16 보안 감사 L-4).

정책 API가 준 주소는 화면의 「신청하러 가기」·원문 링크가 돼요. 예전엔 그대로 옮겨서 javascript:·data:·intent: 같은 주소나
사용자 정보(user@host)가 든 주소도 링크로 나갈 수 있었어요. 수집 단계에서 아래 규칙에 맞는 주소만 남기고 나머지는 비워요(링크 없음).
extraction도 같은 규칙으로 한 번 더 봐요(mujuthaek_extraction/links.py).
- http·https만. 「scheme://호스트」 꼴이어야 하고 사용자 정보(user:pass@)는 안 돼요
- 빈칸·제어 문자·보이지 않는 서식 문자(방향 바꿈 등)·역슬래시가 든 주소, MAX_LINK_CHARS자보다 긴 주소는 안 돼요
- 사설·루프백 IP, localhost, 브라우저가 IP로 읽는 숫자 호스트(2130706433, 0x7f.1)는 안 돼요(공개 기관 링크가 아니에요)
- 「www.youthcenter.go.kr/…」처럼 scheme 없이 도메인으로 시작하면 https://를 붙여요(extraction의 같은 규칙과 같음)
- scheme은 소문자로 바꿔 돌려줘요(계약 패턴 ^https?://가 대소문자를 가려요)
"""

from __future__ import annotations

import ipaddress
import re
import unicodedata
from typing import Any
from urllib.parse import urlsplit

MAX_LINK_CHARS = 2000
# scheme 없이 도메인으로 시작하는 주소: 마지막 이름이 글자(최상위 도메인)여야 해요(「3.14」「1.5배」는 주소가 아니에요)
BARE_HOST = re.compile(r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+(?:[a-z]{2,63}|xn--[a-z0-9-]{1,59})(?::\d{1,5})?(?:[/?#].*)?", re.IGNORECASE)
HOST_NAME = re.compile(r"[\w-]+(?:\.[\w-]+)*")  # 한글 도메인(IDN)도 받아요. %·@ 같은 글자는 안 돼요
NUMERIC_LABEL = re.compile(r"\d+|0x[0-9a-f]*", re.IGNORECASE)
UNSAFE_CATEGORIES = {"Cc", "Cf", "Cs", "Co", "Cn", "Zs", "Zl", "Zp"}


def _unsafe(char: str) -> bool:
    return char == "\\" or char.isspace() or unicodedata.category(char) in UNSAFE_CATEGORIES


def _public_host(host: str) -> bool:
    host = host.rstrip(".")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None:
        return address.is_global and not address.is_multicast
    if host == "localhost" or host.endswith(".localhost"):
        return False
    # 마지막 이름이 숫자·16진수면 브라우저는 IPv4로 읽어요(http://2130706433/ = 127.0.0.1). 점 네 개 꼴이 아닌 숫자 호스트는 받지 않아요
    if NUMERIC_LABEL.fullmatch(host.rsplit(".", 1)[-1]):
        return False
    return bool(HOST_NAME.fullmatch(host))


def public_link(value: Any) -> str | None:
    """사람에게 보여 줄 수 있는 http(s) 주소면 그 주소(scheme은 소문자, 앞뒤 공백 없음), 아니면 None."""
    if not isinstance(value, str):
        return None
    url = value.strip()
    if not url or len(url) > MAX_LINK_CHARS or any(_unsafe(c) for c in url):
        return None
    if "://" not in url and BARE_HOST.fullmatch(url):
        url = "https://" + url
        if len(url) > MAX_LINK_CHARS:
            return None
    try:
        parts = urlsplit(url)
        host = parts.hostname
        parts.port  # noqa: B018 — 포트가 숫자가 아니거나 범위를 넘으면 ValueError
    except ValueError:
        return None
    if parts.scheme not in ("http", "https") or not host or "@" in parts.netloc or not _public_host(host):
        return None
    return parts.scheme + url[len(parts.scheme) :]
