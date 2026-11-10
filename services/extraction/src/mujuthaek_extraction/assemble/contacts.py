"""문의처 코드 보충: 원문의 문의처 줄(「◦문의처 : 051-810-9905~8」「문의전화는 … 공급상담실(031-466-0188)로」)에 있는 전화번호가
안내(guidance)에 하나도 없으면 코드가 CONTACT 항목을 넣습니다.

2026-11-09 23건 bmc-75: 일정·안내 담당이 공고 끝 「| 임대문의 | ◦문의처 : 051-810-9905~8 … |」를 넣지 않아 문의처가 없었음(V1은 넣음).
결합기는 섹션마다 처음 받은 조각만 쓰므로, 안내 목록이 있는 조각에 AI 출력과 같은 모양(인용 포함)으로 덧붙여 결합·검증을 같은 길로 지납니다.
「문의·연락처·콜센터」 낱말 뒤 가까이 있는 번호만 보고, 휴대전화(010 등)는 예시·개인 번호일 수 있어 보지 않습니다. 그림 판독 글은 보지 않습니다.
"""

from __future__ import annotations

import copy
import re
from typing import Any

CONTACT_LABEL = re.compile(r"문의|연락처|콜센터|상담\s*전화")
# 지역번호·대표번호(1588-0000). 「051-810-9905~8」처럼 끝 번호를 물결표로 이어 적은 범위도 한 번호로 봅니다
PHONE = re.compile(r"(?<![\d-])(?:0(?:2|[3-6]\d|70|80)\s*[)\-.]?\s*\d{3,4}\s*[\-.]\s*\d{4}|1[5-9]\d{2}\s*-\s*\d{4})(?:\s*~\s*\d{1,4})?(?![\d-])")
LABEL_TO_PHONE_CHARS = 60  # 문의 낱말 끝에서 번호 시작까지
# 번호 바로 앞의 팩스 표시(「(팩스 : 051-…)」「팩스(02-…)」「팩스번호는 02-…」「FAX 02-…」「F. 02-…」). 문의처 줄에 함께 적힌 팩스 번호를
# 전화번호로 넣었어요(2026-11-10 코드 검토). 「TF」「T/F」「Staff」처럼 영문 낱말 끝의 F는 팩스가 아니에요(재검토: 그 전화번호를 뺐음)
FAX_BEFORE = re.compile(r"(?:팩스|(?<![A-Za-z/])fax|(?<![A-Za-z/])F)\s*(?:번호)?\s*(?:는|은)?\s*[.:：()\]]?\s*$", re.IGNORECASE)
FAX_WINDOW_CHARS = 10
TITLE_CHARS = 20
IMAGE_BLOCK_HEAD = "=== 그림 판독 "  # image_reading.BLOCK_HEAD와 같음
CODE_REF = "code-contact-"


def _number(phone: str) -> str:
    """번호를 견줄 열쇠: 범위(「~8」)를 뗀 숫자."""
    return re.sub(r"\D", "", phone.split("~")[0])


def _scope() -> dict[str, Any]:
    return {
        "level": "NOTICE",
        "locationIds": [],
        "supplyGroupIds": [],
        "targetGroups": [],
        "supplyCategory": "ALL",
        "resolution": "RESOLVED",
        "description": "공고 전체에 적용해요.",
    }


def _title(line: str, label: re.Match[str]) -> str:
    """표 행이면 문의 낱말이 든 칸(「임대문의」), 아니면 「문의처」."""
    if line.lstrip().startswith("|"):
        start = line.rfind("|", 0, label.start()) + 1
        end = line.find("|", label.end())
        cell = " ".join(line[start : end if end >= 0 else len(line)].split())
        if cell and len(cell) <= TITLE_CHARS and not PHONE.search(cell):
            return cell
    return "문의처"


def missing_contacts(guidance: list[Any], text: str) -> list[tuple[str, str, str]]:
    """안내에 없는 문의처 번호마다 (제목, 번호 원문 표기, 인용할 원문 조각)."""
    have = {_number(m[0]) for g in guidance if isinstance(g, dict) and g.get("phone") for m in PHONE.finditer(str(g["phone"]))}
    found: list[tuple[str, str, str]] = []
    for line in text.split(IMAGE_BLOCK_HEAD, 1)[0].split("\n"):
        label = CONTACT_LABEL.search(line)
        if label is None:
            continue
        previous = label.end()
        for match in PHONE.finditer(line, label.end()):
            if match.start() - label.end() > LABEL_TO_PHONE_CHARS:
                break
            before, previous = line[previous : match.start()][-FAX_WINDOW_CHARS:], match.end()
            if FAX_BEFORE.search(before):
                continue
            key = _number(match[0])
            if key in have:
                continue
            have.add(key)
            # 인용은 문의 낱말이 든 낱말 처음(「임대문의」)부터 번호 끝까지 원문 그대로(번호가 문의처 줄의 것임을 함께 보여 줌)
            start = max(line.rfind(" ", 0, label.start()), line.rfind("|", 0, label.start())) + 1
            found.append((_title(line, label), " ".join(match[0].split()), line[start : match.end()].strip()))
    return found


def fill_contacts(parts: list[Any], text: str, document_id: str) -> list[Any]:
    """안내 목록이 있는 첫 조각에, 안내에 없는 문의처 번호마다 CONTACT 항목을 덧붙인 조각 목록(그 밖의 조각은 그대로)."""
    index = next((i for i, p in enumerate(parts) if isinstance(p, dict) and isinstance(p.get("guidance"), list)), None)
    if index is None:
        return parts
    found = missing_contacts(parts[index]["guidance"], text)
    if not found:
        return parts
    part = copy.deepcopy(parts[index])
    part.setdefault("quotes", [])
    for number, (title, phone, quote) in enumerate(found, start=1):
        ref = f"{CODE_REF}{number}"
        part["quotes"].append({"ref": ref, "documentId": document_id, "text": quote})
        part["guidance"].append(
            {
                "id": f"contact-code-{number}",
                "kind": "CONTACT",
                "title": title,
                "description": f"{title} 전화번호예요.",
                "scope": _scope(),
                "phone": phone,
                "url": None,
                "quoteRefs": [ref],
            }
        )
    return [*parts[:index], part, *parts[index + 1 :]]
