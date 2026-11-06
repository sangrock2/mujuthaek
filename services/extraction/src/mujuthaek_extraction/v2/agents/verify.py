"""검증 미들웨어(LangChain AgentMiddleware.before_model): 담당이 도구로 초안을 바꾼 차례 다음, 모델을 부르기 전에 초안을 V1 결합·검증기로 보고
맡은 섹션의 문제를 「검증 결과」 메시지로 넣습니다.

2026-11-06 두 번째 실제 실행: check 도구를 따로 부르게 했더니 부르는 데 차례가 하나 더 들고, 결합기가 형식 오류로 응답 전체를 버리는 것을
「범위 미완료」로만 보여 줘 담당이 범위만 바꾸고 끝냄(선정 규칙 21개 → 0개). 미들웨어는 바뀐 차례마다 빠짐없이, 차례를 더 쓰지 않고 알립니다.

검증 결과는 사람이 확인할 후보입니다. 2026-11-06 세 번째 실제 실행: 원문상 맞는 항목에 걸린 경고(기준값 뒤 140%가 예외 같다)를 없애려고
담당이 없는 예외를 넣었다 빼며 차례 상한까지 돌고, 끝내 섹션 전체를 PARTIAL(전체 검수)로 표시함. 그래서
- 원문과 대조해 실제로 틀렸거나 빠진 것만 고치고, 경고를 없애려고 값을 넣거나 바꾸지 않게 알리고
- 앞 차례에도 있던 문제는 「다시」로 표시해, 한 번 고쳐 보고도 남으면 그대로 두고 끝내게 합니다(그 항목만 사람이 확인).

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
GUIDE = (
    "검증 결과는 사람이 확인할 후보입니다. 원문과 대조해 실제로 틀렸거나 빠진 것만 고칩니다(update_item·remove_item·add, 원문에 없는 값은 report_missing). "
    "원문상 맞으면 그대로 둡니다(그 항목만 사람이 확인). 경고를 없애려고 원문에 없는 값·예외를 넣거나 맞는 값을 바꾸지 않습니다. "
    "「다시」 표시는 앞 차례에도 있던 문제입니다: 한 번 고쳐 보고도 남았으면 더 고치지 않습니다. "
    "set_coverage(PARTIAL)는 원문에 있는데 넣지 못한 항목이 있을 때만 씁니다(섹션 전체가 사람 확인으로 감). "
    "고칠 것을 고치는 차례에 finish도 함께 부르고, 고칠 것이 없으면 finish만 부릅니다."
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
        fresh = [issue for issue in issues if _key(issue) not in self.reported]
        if draft.finished and not fresh:
            return {"jump_to": "end"}  # 끝내기를 불렀고 새 문제가 없음: 모델을 다시 부르지 않음
        draft.finished = None  # 새 문제가 있으면 끝내기를 거두고 알림
        marked = [{**issue, "다시": True} if _key(issue) in self.reported else issue for issue in issues]
        self.reported |= {_key(issue) for issue in issues}
        return {"messages": [HumanMessage(report(draft, marked))]}


def report(draft: Any, issues: list[dict[str, Any]]) -> str:
    counts = {section: len(draft.items.get(section, [])) for section in draft.sections}
    lines = ["# 검증 결과(프로그램이 지금 초안을 V1 결합·검증기로 본 것)", f"맡은 섹션 항목 수: {json.dumps(counts, ensure_ascii=False)}"]
    if not issues:
        lines.append("맡은 섹션에 남은 문제가 없습니다. 원문에서 빠뜨린 항목이 없으면 finish를 부릅니다.")
        return "\n".join(lines)
    shown = f" (앞 {ISSUES_SHOWN}개)" if len(issues) > ISSUES_SHOWN else ""
    lines.append(f"문제 {len(issues)}개{shown}:")
    lines += [json.dumps(issue, ensure_ascii=False) for issue in issues[:ISSUES_SHOWN]]
    lines.append(GUIDE)
    return "\n".join(lines)


def _key(issue: dict[str, Any]) -> tuple[str, str, str]:
    """같은 문제인지: 코드·항목 id·항목 안 위치(항목을 빼면 목록 순번이 바뀌므로 순번은 빼고 셈)."""
    tokens = str(issue.get("target") or "").strip("/").split("/")
    inside = "/".join(tokens[2:]) if issue.get("item") and len(tokens) >= 2 and tokens[1].isdigit() else "/".join(tokens)
    return str(issue.get("code")), str(issue.get("item") or ""), inside
