"""검증 미들웨어(LangChain AgentMiddleware.before_model): 담당이 도구로 초안을 바꾼 차례 다음, 모델을 부르기 전에 초안을 V1 결합·검증기로 보고
맡은 섹션의 문제를 「검증 결과」 메시지로 넣습니다.

2026-11-06 두 번째 실제 실행: check 도구를 따로 부르게 했더니 부르는 데 차례가 하나 더 들고, 결합기가 형식 오류로 응답 전체를 버리는 것을
「범위 미완료」로만 보여 줘 담당이 범위만 바꾸고 끝냄(선정 규칙 21개 → 0개). 미들웨어는 바뀐 차례마다 빠짐없이, 차례를 더 쓰지 않고 알립니다.
담당은 그 결과로 고치거나, 고칠 것이 없으면 도구 없이 끝냅니다.
"""

from __future__ import annotations

import json
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import HumanMessage

ISSUES_SHOWN = 20


class VerifyMiddleware(AgentMiddleware):
    def __init__(self) -> None:
        super().__init__()
        self.seen = 0  # 마지막으로 알린 초안 판(SectionDraft.version)

    def before_model(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        context = runtime.context
        draft = getattr(context, "draft", None)
        if draft is None or context.check is None or draft.version == self.seen:
            return None
        self.seen = draft.version
        return {"messages": [HumanMessage(report(draft, context.check()))]}


def report(draft: Any, issues: list[dict[str, Any]]) -> str:
    counts = {section: len(draft.items.get(section, [])) for section in draft.sections}
    lines = ["# 검증 결과(프로그램이 지금 초안을 V1 결합·검증기로 본 것)", f"맡은 섹션 항목 수: {json.dumps(counts, ensure_ascii=False)}"]
    if not issues:
        lines.append("맡은 섹션에 남은 문제가 없습니다. 원문에서 빠뜨린 항목이 없으면 도구 없이 끝냅니다.")
        return "\n".join(lines)
    shown = f" (앞 {ISSUES_SHOWN}개)" if len(issues) > ISSUES_SHOWN else ""
    lines.append(f"문제 {len(issues)}개{shown}:")
    lines += [json.dumps(issue, ensure_ascii=False) for issue in issues[:ISSUES_SHOWN]]
    lines.append(
        "원문으로 고칠 수 있는 것은 update_item·remove_item·add로 고치고, 판정·화면에 필요한데 원문에 없는 값은 report_missing으로 적습니다. "
        "고칠 수 없는 것만 남으면 set_coverage(PARTIAL)로 이유를 적고 끝냅니다."
    )
    return "\n".join(lines)
