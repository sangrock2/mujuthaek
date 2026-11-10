"""LH 상세정보·공급정보·마이홈 응답을 파이프라인이 쓰는 모양(본문 글자, 항목, 시군구 코드)으로 바꿔요.

본문 글자(body_text)는 '바뀐 것만 새 버전'을 판단하는 해시와 AI 추출 글자에 들어가요. 그래서
- 부를 때마다 바뀌는 값(응답 시각 resHeader, 요청 값 dsSch)은 넣지 않고
- 칸 순서를 고정하고, 칸 이름은 응답에 같이 오는 한글 설명(…Nm)을 써요.
"""

from __future__ import annotations

import re
from typing import Any

from mujuthaek_collector.sources.lh.parse import merge_blocks

META_BLOCKS = {"dsSch", "resHeader"}
SKIP_BLOCKS = {"dsSbdAhfl"}  # 단지 사진(조감도·평면도) 목록: AI 추출과 바뀜 판단에 쓸모가 없어요 (원본에는 남아요)
SECTIONS = [  # (묶음, 제목) — 이 순서로 써요. 여기 없는 묶음은 이름 순서로 뒤에 붙여요
    ("dsSplScdl", "공급일정"),
    ("dsSbd", "단지"),
    ("dsCtrtPlc", "접수처"),
    ("dsEtcInfo", "기타사항"),
    ("dsEtcList", "신청자격"),
    ("dsAhflInfo", "첨부"),
]
EMPTY = {"", "~", "-"}
# 첨부 다운로드 주소는 빼요: 파일 내용은 첨부 해시로 따로 비교하고, 같은 파일인데 번호만 다시 매겨도 새 버전이 되지 않게
SKIP_KEYS = {"AHFL_URL"}

# 마이홈 줄에서 본문에 쓰는 칸 (마이홈 응답에는 칸 이름 설명이 없어서 직접 붙여요)
MYHOME_FIELDS = [
    ("hsmpNm", "단지"),
    ("fullAdres", "주소"),
    ("brtcNm", "시도"),
    ("signguNm", "시군구"),
    ("pnu", "필지번호"),
    ("houseTyNm", "주택유형"),
    ("suplyTyNm", "공급유형"),
    ("sumSuplyCo", "공급호수"),
    ("rentGtn", "임대보증금(원)"),
    ("mtRntchrg", "월임대료(원)"),
    ("enty", "계약금(원)"),
    ("prtpay", "중도금(원)"),
    ("surlus", "잔금(원)"),
    ("beginDe", "접수시작"),
    ("endDe", "접수마감"),
    ("przwnerPresnatnDe", "당첨자발표"),
    ("sttusNm", "공고상태"),
    ("pblancId", "마이홈공고ID"),
]


def _text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value)).strip() if value is not None else ""


def split_blocks(body: Any) -> tuple[dict[str, list[dict[str, Any]]], dict[str, dict[str, str]]]:
    """(데이터 묶음, 칸 이름 설명). 요청 값·응답 시각 묶음은 빼요."""
    merged = merge_blocks(body)
    data = {k: v for k, v in merged.items() if k not in META_BLOCKS and not k.endswith("Nm")}
    labels = {k[:-2]: v[0] for k, v in merged.items() if k.endswith("Nm") and v}
    return data, labels


def _rows_text(rows: list[dict[str, Any]], labels: dict[str, str]) -> list[str]:
    lines = []
    for row in rows:
        keys = [k for k in labels if k in row and k not in SKIP_KEYS] + sorted(k for k in row if k not in labels and k not in SKIP_KEYS)
        parts = [f"{labels.get(k, k)}: {_text(row[k])}" for k in keys if _text(row[k]) not in EMPTY]
        if parts:
            lines.append(" | ".join(parts))
    return lines


def body_text(detail_body: Any, supply_body: Any, myhome_entries: list[dict[str, Any]]) -> str:
    data, labels = split_blocks(detail_body)
    order = [name for name, _ in SECTIONS if name in data]
    order += sorted(k for k in data if k not in order and k not in SKIP_BLOCKS)
    titles = dict(SECTIONS)
    lines: list[str] = []
    for name in order:
        rows = _rows_text(data[name], labels.get(name, {}))
        if rows:
            lines += [f"[{titles.get(name, name)}]", *rows]

    supply, supply_labels = split_blocks(supply_body)
    for name in sorted(supply):
        rows = _rows_text(supply[name], supply_labels.get(name, {}))
        if rows:
            lines += [f"[공급정보 {name}]", *rows]

    if myhome_entries:
        lines.append("[마이홈] 단지마다 한 줄 (금액은 단지의 주택형 하나 값이에요)")
        for entry in sorted(myhome_entries, key=lambda e: e["key"]):
            item = entry["item"]
            parts = [f"{label}: {_text(item.get(key))}" for key, label in MYHOME_FIELDS if _text(item.get(key)) not in EMPTY | {"0"}]
            lines.append(" | ".join(parts))
    return "\n".join(lines)


def region_code(myhome_entries: list[dict[str, Any]]) -> str | None:
    """마이홈 필지번호(pnu, 19자리) 앞 5자리 = 시군구 코드. LH API에는 시군구 코드가 없어요."""
    for entry in sorted(myhome_entries, key=lambda e: e["key"]):
        pnu = _text(entry["item"].get("pnu"))
        if re.fullmatch(r"\d{19}", pnu):
            return pnu[:5]
    return None


def lh_meta(row: dict[str, str]) -> dict[str, str]:
    """AI 추출 글자에 들어가는 목록 항목 (사람이 읽는 이름으로)."""
    fields = {"공고유형": "AIS_TP_CD_NM", "상위유형": "UPP_AIS_TP_NM", "지역": "CNP_CD_NM", "공고상태": "PAN_SS", "마감일": "CLSG_DT"}
    return {label: _text(row.get(code)) for label, code in fields.items() if _text(row.get(code))}
