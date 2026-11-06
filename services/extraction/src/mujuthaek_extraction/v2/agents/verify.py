"""검증 미들웨어(LangChain AgentMiddleware.before_model): 담당이 도구로 초안을 바꾼 차례 다음, 모델을 부르기 전에 초안을 V1 결합·검증기로 보고
맡은 섹션의 문제를 「검증 결과」 메시지로 넣습니다.

2026-11-06 두 번째 실제 실행: check 도구를 따로 부르게 했더니 부르는 데 차례가 하나 더 들고, 결합기가 형식 오류로 응답 전체를 버리는 것을
「범위 미완료」로만 보여 줘 담당이 범위만 바꾸고 끝냄(선정 규칙 21개 → 0개). 미들웨어는 바뀐 차례마다 빠짐없이, 차례를 더 쓰지 않고 알립니다.

검증 결과는 사람이 확인할 후보입니다. 2026-11-06 세 번째 실제 실행: 원문상 맞는 항목에 걸린 경고(기준값 뒤 140%가 예외 같다)를 없애려고
담당이 없는 예외를 넣었다 빼며 차례 상한까지 돌고, 끝내 섹션 전체를 PARTIAL(전체 검수)로 표시함. 그래서
- 원문과 대조해 실제로 틀렸거나 빠진 것만 고치고, 경고를 없애려고 값을 넣거나 바꾸지 않게 알리고
- 앞 차례에도 있던 문제는 「다시」로 표시해, 한 번 고쳐 보고도 남으면 그대로 두고 끝내게 합니다(그 항목만 사람이 확인).

검증 결과는 두 갈래로 알립니다(2026-11-06 다섯 번째 실제 실행: 「다시」면 멈추라는 규칙에 id 중복 같은 계약 오류까지 멈춰, 고칠 수 있던
조건이 격리됨). 「고칠 것」(형식·계약·근거 오류)은 그대로 두면 값이 빠지거나 사람 확인으로 가므로 「다시」여도 다른 방법으로 고치고,
「확인할 것」(의심 경고)만 원문상 맞으면 그대로 두고 「다시」면 더 고치지 않습니다.

끝내기(finish): 담당이 마지막 고치기와 같은 차례에 finish를 부르면, 그 차례 도구가 실행된 뒤 새 문제(앞서 알리지 않은 것)가 없으면 모델을 다시
부르지 않고 끝냅니다. 새 문제가 있으면 끝내기를 거두고 알립니다. 「끝났어요」만 답하는 마지막 차례가 없어집니다(2026-11-06 네 번째 실행:
그 차례가 담당마다 하나씩 들고, 캐시를 못 읽으면 앞부분 6만 토큰을 다시 씀).
"""

from __future__ import annotations

import json
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import hook_config
from langchain_core.messages import HumanMessage

ISSUES_SHOWN = 20
# 형식·계약·근거 오류: 원문과 상관없이 객관적인 결함이라 고침(그대로 두면 값이 빠지거나 사람 확인으로 감). 근거를 바꾸는 고치기는 값을 바꾸지 않음.
# 조건식 없음(CRITERION_NOT_STRUCTURED)·예외 의심 같은 판단 경고는 넣지 않음: 「자산기준: 배제」처럼 원문상 조건식이 없는 게 맞을 때 없는 값을 넣게 됨
MUST_FIX = (
    "FORMAT_",
    "CONTRACT_",
    "AI_OUTPUT_",
    "NOT_ASSEMBLED",
    "VALUE_NOT_IN_QUOTE",
    "EVIDENCE_",
    "ORIGINAL_TEXT_NOT_FOUND",
    "QUOTE_REF_UNKNOWN",
    "ITEM_DROPPED",
    "ITEM_NOT_ADDED",
    "CLAIM_UNSUPPORTED",
)
FIX_GUIDE = (
    "고칠 것: 형식·계약·근거 오류입니다. 그대로 두면 값이 빠지거나 사람 확인으로 가므로 원문에 있는 대로 고칩니다. "
    "「다시」면 앞서 고친 방법이 안 된 것이니 다른 방법으로 한 번 더 고치고, 그래도 남으면 그대로 둡니다."
)
CHECK_GUIDE = (
    "확인할 것: 의심 경고입니다. 원문과 대조해 실제로 틀렸거나 빠졌을 때만 고치고, 원문상 맞으면 그대로 둡니다(그 항목만 사람이 확인). "
    "경고를 없애려고 원문에 없는 값·예외를 넣거나 맞는 값을 바꾸지 않습니다. 「다시」 표시는 한 번 고쳐 보고도 남은 것이라 더 고치지 않습니다."
)
# 경고 옆에 다시 보여 주는 고치는 법(공통 지시의 그 규칙). 2026-11-06 23건 측정: 대상군·출생자녀 수에 따라 한도가 달라지는 자산 기준을
# 「하나의 조건식으로 표현할 수 없다」며 글로만 남기고 경고를 받고도 그대로 둠(V1은 기본 한도 + 자녀 수별 예외로 넣음, 16값 차이)
HOW_TO = {
    "CRITERION_NOT_STRUCTURED": (
        "기준값이 대상군·자녀 수·배우자 소득 등에 따라 달라진다는 것만으로는 글로 남길 이유가 아닙니다. 대상군마다 기준이 다르면 대상군마다 조건을 "
        "따로 두고, 한 조건 안에서 달라지는 값은 기본 기준을 조건식으로, 달라지는 경우를 exceptions(REPLACE, effectExpression 필수, 발동 조건을 "
        "다 표현할 수 없으면 when.status UNSTRUCTURED)로 넣습니다. 이번 모집에 적용하지 않는 기준이거나 속성 사전으로 나타낼 수 없는 기준이면 그대로 둡니다."
    ),
    "CONTRACT_INCOMPLETE_INCOME_BENCHMARK": (
        "소득 기준(INCOME_BENCHMARK_PERCENT)의 benchmark에는 householdScope와, referenceYear·referenceVersion 중 하나가 꼭 있어야 합니다. "
        "원문에 기준 연도가 없으면 연도를 짐작해 넣지 말고 referenceVersion에 원문의 기준 표현(「전년도」「입주자모집공고일 당시」 등)을 그대로 적습니다."
    ),
    "CONTRACT_EXCEPTIONS_NOT_REVIEWED": (
        "exceptionsStatus를 NOT_REVIEWED로 두지 않습니다. 원문에 그 조건의 예외가 없으면 NONE_IN_SOURCE, 있으면 PRESENT와 exceptions를 적습니다."
    ),
    "DEFINITION_SCOPE_SUSPECTED": (
        "원문이 어떤 낱말(고령자 등)의 정의라면 그 기준은 그 낱말에 해당하는 사람에게만 적용됩니다. 대상(scope.targetGroups)을 그 낱말이 든 이름으로 "
        "좁힙니다(예: 「○○ 신청자 중 고령자」). 원문상 대상 전체의 기준이 맞으면 그대로 둡니다."
    ),
}
END_GUIDE = (
    "원문에 없는 값은 report_missing으로 적습니다. set_coverage(PARTIAL)는 원문에 있는데 넣지 못한 항목이 있을 때만 씁니다(섹션 전체가 사람 확인으로 감). "
    "고치는 차례에 finish도 함께 부르고, 고칠 것이 없으면 finish만 부릅니다."
)


class VerifyMiddleware(AgentMiddleware):
    def __init__(self) -> None:
        super().__init__()
        self.seen = 0  # 마지막으로 알린 초안 판(SectionDraft.version)
        self.reported: set[tuple[str, str, str]] = set()  # 앞서 알린 문제(코드·위치·항목)

    @hook_config(can_jump_to=["end"])
    def before_model(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        context = runtime.context
        draft = getattr(context, "draft", None)
        if draft is None or context.check is None:
            return None
        if draft.version == self.seen:
            return {"jump_to": "end"} if draft.finished else None
        self.seen = draft.version
        issues = context.check()
        fresh = [issue for issue in issues if issue_key(issue) not in self.reported]
        if draft.finished and not fresh:
            return {"jump_to": "end"}  # 끝내기를 불렀고 새 문제가 없음: 모델을 다시 부르지 않음
        draft.finished = None  # 새 문제가 있으면 끝내기를 거두고 알림
        marked = [{**issue, "다시": True} if issue_key(issue) in self.reported else issue for issue in issues]
        self.reported |= {issue_key(issue) for issue in issues}
        return {"messages": [HumanMessage(report(draft, marked))]}


def report(draft: Any, issues: list[dict[str, Any]]) -> str:
    counts = {section: len(draft.items.get(section, [])) for section in draft.sections}
    lines = ["# 검증 결과(프로그램이 지금 초안을 V1 결합·검증기로 본 것)", f"맡은 섹션 항목 수: {json.dumps(counts, ensure_ascii=False)}"]
    if not issues:
        lines.append("맡은 섹션에 남은 문제가 없습니다. 원문에서 빠뜨린 항목이 없으면 finish를 부릅니다.")
        return "\n".join(lines)
    fix = [issue for issue in issues if must_fix(issue)]
    check = [issue for issue in issues if not must_fix(issue)]
    for title, group, guide in (("고칠 것", fix, FIX_GUIDE), ("확인할 것", check, CHECK_GUIDE)):
        if group:
            shown = f" (앞 {ISSUES_SHOWN}개)" if len(group) > ISSUES_SHOWN else ""
            lines += [f"## {title} {len(group)}개{shown}", guide, *(json.dumps(issue, ensure_ascii=False) for issue in group[:ISSUES_SHOWN])]
    hints = [f"- {code}: {HOW_TO[code]}" for code in dict.fromkeys(str(issue.get("code")) for issue in issues) if code in HOW_TO]
    if hints:
        lines += ["## 고치는 법", *hints]
    lines.append(END_GUIDE)
    return "\n".join(lines)


def must_fix(issue: dict[str, Any]) -> bool:
    return str(issue.get("code") or "").startswith(MUST_FIX)


def issue_key(issue: dict[str, Any]) -> tuple[str, str, str]:
    """같은 문제인지: 코드·항목 id·항목 안 위치(항목을 빼면 목록 순번이 바뀌므로 순번은 빼고 셈)."""
    tokens = str(issue.get("target") or "").strip("/").split("/")
    inside = "/".join(tokens[2:]) if issue.get("item") and len(tokens) >= 2 and tokens[1].isdigit() else "/".join(tokens)
    return str(issue.get("code")), str(issue.get("item") or ""), inside
