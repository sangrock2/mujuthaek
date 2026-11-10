"""판정 틀 가공: 검증까지 끝난 후보를 판정 담당이 정한 틀(contracts/schemas/*-judgment.v1.json) 그대로의 객체로 바꿉니다.

틀은 판정 담당이 준 그대로 유지합니다(사용자 결정 2026-10-20: 이름·칸·값을 바꾸지 않고 우리 출력을 맞춤).
코드만 씁니다(AI 호출 없음). 후보에 구조화된 값이 있으면 그대로 옮기고, 코드로 정할 수 없는 조건은 틀 안의 수단
(원문 문장 질문 ASK, inReview와 이유, notes)으로 보냅니다. 결과는 틀의 JSON Schema 원본과 ID 유일성으로 검사하고,
통과하지 못하면 None(이벤트의 judgment는 null)을 돌려줍니다.
"""

from __future__ import annotations

from functools import cache
from typing import Any

from mujuthaek_extraction.judgment.business_space import build_business_space
from mujuthaek_extraction.judgment.housing import build_housing
from mujuthaek_extraction.judgment.pages import fill_pages, quote_pages
from mujuthaek_extraction.judgment.sanity import repair
from mujuthaek_extraction.judgment.schema import frame_errors

BUILDERS = {"HOUSING": build_housing, "BUSINESS_SPACE": build_business_space}


@cache
def default_regions() -> Any:
    """지역표를 넘기지 않은 곳(검수 승인 등)에서도 같은 결과가 나오게 서비스 기본 지역표를 씁니다. 없으면 None(거주 문장은 질문으로)."""
    from mujuthaek_extraction.assemble.regions import RegionCodeTable
    from mujuthaek_extraction.config import Settings

    fields = Settings.__dataclass_fields__
    path, when = fields["region_table"].default, fields["region_table_date"].default
    try:
        return RegionCodeTable.from_csv(path, when)
    except OSError:
        return None


def build_judgment(candidate: dict[str, Any], regions: Any = None, *, approved: bool = False, pages: dict[str, int] | None = None) -> dict[str, Any] | None:
    """후보 → 판정 틀 객체. 틀이 없는 분야(정책·창업지원)이거나 틀 검사를 통과하지 못하면 None.
    approved: 검수자가 승인한 결과(추출 검수 사유로는 inReview를 붙이지 않음).
    pages: 근거 ID → PDF 쪽 번호(judgment/pages.py). 있으면 조건·안내의 page를 그 항목 근거의 쪽으로 채웁니다."""
    builder = BUILDERS.get(candidate["input"]["field"])
    if builder is None:
        return None
    # 거꾸로 된 범위·빈 글자는 그 조건만 확인 필요 질문으로(값 하나 때문에 틀 전체가 버려지지 않게)
    frame = repair(builder(candidate, regions if regions is not None else default_regions(), approved=approved))
    if frame is not None and pages:
        fill_pages(frame, quote_pages(candidate, pages))
    if frame is None or frame_errors(frame):
        return None
    return frame
