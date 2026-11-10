"""LH 공고 분류: 상세를 열 공고(모집·정정)와 열지 않을 공고(취소·제외)를 나눠요.

LH는 목록에 공고 유형 칸(UPP_AIS_TP_NM·AIS_TP_CD_NM)이 있어서 공통 분류기(제목 규칙) 대신 이걸 써요.
공통 분류기는 LH의 '…잔여세대 선착순 일반매각 공고'를 제외로, '(순번추첨 동호지정)'이 붙은 모집공고를
후속 안내로 봐요. 그래서 LhSource.pre_classify가 항상 이 결과를 돌려줘요.
게시 1년이 지난 공고는 파이프라인이 먼저 건너뛰어요(Settings.since_days).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from mujuthaek_collector.core import classify as cls
from mujuthaek_collector.sources.lh import config

HOUSING = {"임대주택", "분양주택", "공공분양(신혼희망)", "주거복지"}
SALE = {"분양주택", "공공분양(신혼희망)"}
EXCLUDE_TITLE = re.compile(
    r"택지|용지|보상|사업자\s*(공모|모집)|운영(예정)?자\s*모집|평가위원"
    r"|(주택|건물)\s*매입\s*(신청|공고|공모)|매입\s*약정|매도\s*신청"
)
CORRECTION = re.compile(r"\[\s*정정\s*(공고)?\s*\]|\(\s*정정\s*\)|정정공고")
CANCEL = re.compile(r"\[\s*취소\s*(공고)?\s*\]|취소공고")


@dataclass(frozen=True)
class Classification:
    kind: str  # 모집공고 | 정정공고 | 취소공고 | 제외
    category: str | None  # 임대 | 분양 | 사업공간
    reason: str | None = None  # 제외 사유

    @property
    def pipeline_kind(self) -> str:
        """파이프라인 종류(raw_posts.kind). 취소공고는 이벤트 계약에 종류가 없어서 열지 않아요(EXCLUDED)."""
        return {"모집공고": cls.NOTICE, "정정공고": cls.CORRECTION}.get(self.kind, cls.EXCLUDED)


def _by_title(title: str, category: str | None) -> Classification:
    m = EXCLUDE_TITLE.search(title)
    if m:
        return Classification("제외", None, f"제목 '{m.group(0)}'")
    if CANCEL.search(title):
        return Classification("취소공고", category)
    if CORRECTION.search(title):
        return Classification("정정공고", category)
    return Classification("모집공고", category)


def classify(row: dict[str, str], include_business: bool = config.INCLUDE_BUSINESS) -> Classification:
    """LH 목록 한 줄 분류."""
    title = row.get("PAN_NM", "")
    upper = row.get("UPP_AIS_TP_NM", "")
    if upper == "토지":
        return Classification("제외", None, "택지·용지 공급")
    if upper == "상가" and not include_business:
        return Classification("제외", None, "사업공간(상가) - 수집 범위 밖 (INCLUDE_BUSINESS=False)")
    if upper == "상가":
        category = "사업공간"
    elif upper in HOUSING:
        # 행복주택은 상위 유형이 분양주택으로 와도 임대, 잔여세대 '매각'은 분양
        sale = upper in SALE and "행복" not in row.get("AIS_TP_CD_NM", "")
        category = "분양" if sale or "매각" in title else "임대"
    else:
        return Classification("제외", None, f"공고 유형 '{upper}'")
    return _by_title(title, category)


def classify_title(title: str) -> Classification:
    """마이홈에만 보이는 공고: LH 목록 줄이 없어서 제목으로만 나눠요 (마이홈 목록은 주택 공고만 있어요)."""
    return _by_title(title, None)
