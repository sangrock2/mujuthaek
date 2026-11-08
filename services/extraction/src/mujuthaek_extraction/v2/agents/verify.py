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
부르지 않고 끝냅니다. 새 문제가 있거나, 한 번만 알린 「고칠 것」이 남았으면 끝내기를 거두고 알립니다(「다시」로 한 번 더 알린 뒤에는 끝냄).
「끝났어요」만 답하는 마지막 차례가 없어집니다(2026-11-06 네 번째 실행: 그 차례가 담당마다 하나씩 들고, 캐시를 못 읽으면 앞부분 6만 토큰을 다시 씀).
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
    # 원문 기준표에서 대상(공급유형·계층)이 통째로 빠짐: 23건 저장 결과에서 모두 실제 누락이었고(잘못 잡은 것 없음), 「확인할 것」으로는
    # 담당이 다른 경고를 고친 뒤 넘겼음(2026-11-07 유료 확인 jbdc-16011)
    "CRITERIA_GROUP_OMISSION",
    # 가구원 수·자녀 수 구간을 조건 여러 개로 나눔(구간 조건 없음·구간을 그리고로 묶음): 자격 조건은 모두 함께 적용되어 원문과 상관없이 틀림
    # (2026-11-08 유료 확인 dcco-24812: 「확인할 것」으로 받은 구간 조건 누락을 구간을 그리고로 붙인 조건 9개로 「고쳐」 자동 게시)
    "TIER_CONDITION",
)
FIX_GUIDE = (
    "고칠 것: 형식·계약·근거 오류, 원문 기준표에서 통째로 빠진 대상, 구간마다 따로 둔 자격 조건입니다. 그대로 두면 값이 빠지거나 틀리거나 사람 "
    "확인으로 가므로 원문에 있는 대로 고칩니다. "
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
        "다 표현할 수 없으면 when.status UNSTRUCTURED)로 넣습니다. 자동차가 없어야 하는 기준(「자동차를 소유하고 있지 않을 것」)은 "
        "CAR_ASSETS_KRW LTE 0입니다(속성 사전에 EQ가 없음). 금액의 숫자와 단위가 줄바꿈으로 갈라져 있어도(「4,542」 다음 줄 「만원 이하」) "
        "두 줄을 이어 인용하면 검증됩니다. 이번 모집에 적용하지 않는 기준이거나 속성 사전으로 나타낼 수 없는 기준이면 그대로 둡니다."
    ),
    # 2026-11-09 23건 sh-311087: 일정표 밖 번호 붙은 글 줄의 계약체결·입주기간을 일정 담당이 넣지 않음(consistency._check_schedule_rows).
    # 같은 날 남은 놓침: 풀린 순서도(umca-4439)·일정 표의 단계 낱말 없는 칸(gh-809)·연도 없는 날짜(gndc-1239)
    "SCHEDULE_OMISSION_SUSPECTED": (
        "원문에 날짜가 적힌 단계(계약 체결·입주 기간·자격 조사·발표 등, 일정표 밖 「나. 계약체결: …」 같은 글 줄 포함)는 일정으로 넣습니다. "
        "순서도·표가 글로 풀려 단계 이름 줄과 날짜만 이어 적은 줄이 따로 나오면 이름 순서대로 날짜를 짝짓고, 일정 표의 칸은 단계 낱말이 없는 칸"
        "(「적격여부 검수」)도 단계입니다. 연도 없이 적은 날짜(「서류심사 (7.10. ~ 7.14.)」)는 공고 연도로 넣습니다. "
        "그 날짜가 이미 다른 일정의 시작·끝이거나 이번 모집의 단계가 아니면(단지 준공·입주 연월 등) 그대로 둡니다."
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
    # 2026-11-08 유료 확인 bmc-106: 1순위 자격(가~자목 중 하나)의 계층 조건을 대상 없이 넣어 나이 65세 이상·나마바아목만의 소득 상한이 모두에게 걸림
    "SCOPE_SUBGROUP_SUSPECTED": (
        "대상(scope.targetGroups)이 비어 신청자 전체에 함께 걸리는 조건입니다. 원문상 일부 계층(자격 목록의 목·공급유형·순위)의 기준이면 "
        "scope.targetGroups에 그 계층 이름을 적어 그 대상에만 적용합니다(appliesTo는 그 기준을 보는 사람 범위: 신청자·세대구성원 등). "
        "여러 계층 중 하나에 해당하면 되는 자격은 계층마다 대상을 따로 둡니다. 원문상 신청자 모두의 기준이면 그대로 둡니다."
    ),
    # 2026-11-07 23건 원인 분석: 계층×가구원 수×출생자녀 수 가산표의 자산·자동차 행, 공급유형×공급방식×맞벌이 소득표의 행 일부가 조건에 없음
    "CRITERIA_TABLE_OMISSION_SUSPECTED": (
        "기준표의 행마다 기준값이 조건에 있어야 합니다. 행의 대상(계층·공급유형·공급방식)이 다르면 대상마다 조건을 두고, 한 대상 안에서 가구원 수·"
        "자녀 수·출생자녀 수·맞벌이 여부에 따라 바뀌는 값은 그 대상의 기본 기준 조건에 행마다 exceptions(REPLACE, effectExpression은 그 행의 기준값, "
        "발동 조건을 다 표현할 수 없으면 when.status UNSTRUCTURED)로 넣고 그 표 행을 예외의 evidence로 인용합니다(예외 originalText를 비우면 "
        "그 근거 행의 원문으로 채움). 가점·임대조건처럼 신청 자격이 아닌 표이거나 이번 모집에 적용하지 않는 표면 그대로 둡니다."
    ),
    "CRITERIA_GROUP_OMISSION_SUSPECTED": (
        "적힌 대상(공급유형·계층)마다 조건을 따로 만들고 scope.targetGroups에 그 대상 이름을 적습니다. 그 대상의 기준표 행 가운데 대부분 가구에 "
        "적용되는 값을 기본 조건식으로, 맞벌이·가구원 수·출생자녀 수 행은 그 조건의 exceptions(REPLACE)로 넣고 표 행을 evidence로 인용합니다. "
        "원문상 그 대상이 이번 모집의 신청 자격이 아니면(가점·임대조건 표, 이번에 공급하지 않는 유형) 그대로 둡니다."
    ),
    # 2026-11-07 유료 확인(jbdc-16011): 「(2단계) 추첨공급 : … 130% 초과 200% 이하 * 1단계 낙첨자를 포함」을 자격 하한으로 옮김
    "LOWER_BOUND_IN_ELIGIBILITY": (
        "단계별 선정(2단계·3단계)의 소득 구간(「100% 초과 130% 이하」)은 앞 단계 낙첨자를 포함하므로 자격 하한이 아닙니다. 하한을 빼고 그 공급에 "
        "신청할 수 있는 사람 전체의 상한만 조건식으로 둡니다(앞 단계 기준과 구간은 description에). 원문이 그 소득 구간의 신청자만 받는 공급이면 그대로 둡니다."
    ),
}
# 구간마다 따로 둔 자격 조건(구간 조건 없이 값만 다름·구간을 기준과 그리고로 묶음)의 고치는 법: 둘 다 같은 고침
TIER_HOW_TO = (
    "자격 조건은 모두 함께 적용됩니다. 가구원 수·자녀 수(출생자녀 수) 구간마다 기준값이 다르면 그 대상의 그 기준은 조건 하나로 둡니다: 구간 하나"
    "(보통 마지막 「3인 이상」 구간이나 기본 한도)의 값을 기본 조건식으로, 다른 구간은 그 조건의 exceptions(REPLACE, when=그 구간의 가구원 수·"
    "자녀 수 조건, effectExpression=그 구간 기준값)로 넣습니다. 구간을 기준값과 ALL로 묶은 조건을 따로 두지 않습니다(그 구간이 아닌 가구는 자격이 "
    "없게 됨). 구간마다 따로 넣은 조건은 remove_item으로 빼고 기본 조건의 예외로 옮깁니다."
)
HOW_TO["TIER_CONDITION_MISSING"] = HOW_TO["TIER_CONDITION_CONJOINED"] = TIER_HOW_TO
END_GUIDE = (
    "원문에 없는 값은 report_missing으로 적습니다. set_coverage(PARTIAL)는 원문에 있는데 넣지 못한 항목이 있을 때만 씁니다(섹션 전체가 사람 확인으로 감). "
    "고치는 차례에 finish도 함께 부르고, 고칠 것이 없으면 finish만 부릅니다."
)


class VerifyMiddleware(AgentMiddleware):
    def __init__(self) -> None:
        super().__init__()
        self.seen = 0  # 마지막으로 알린 초안 판(SectionDraft.version)
        self.issues: list[dict[str, Any]] = []  # 그 판의 검증 결과
        self.reported: set[tuple[str, str, str]] = set()  # 앞서 알린 문제(코드·위치·항목)
        self.repeated: set[tuple[str, str, str]] = set()  # 「다시」로 한 번 더 알린 문제

    @hook_config(can_jump_to=["end"])
    def before_model(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        context = runtime.context
        draft = getattr(context, "draft", None)
        if draft is None or context.check is None:
            return None
        changed = draft.version != self.seen
        if not changed and not draft.finished:
            return None  # 초안이 그대로인 차례(실패한 고치기만) 뒤에는 다시 알리지 않음
        if changed:
            self.seen = draft.version
            self.issues = context.check()
        issues = self.issues
        fresh = [issue for issue in issues if issue_key(issue) not in self.reported]
        # 한 번만 알린 고칠 것이 남은 채 끝내기: 같은 차례에 부른 고치기가 실패해도 담당은 그 결과를 못 보고 끝남(2026-11-08 최종 비교
        # bmc-106: 거절된 소득·자산·자동차 조건 3개의 고치기가 모두 실패한 차례에 finish도 불러 28값이 빠짐, 23건 중 5개 담당이 같은 꼴).
        # 「다시」로 한 번 더 알리고 끝내기를 거둡니다. 「다시」로 알린 뒤에도 남으면 끝냄(고칠 것 안내대로 두 번 고쳐 보고 둠)
        unsettled = [issue for issue in issues if must_fix(issue) and issue_key(issue) not in self.repeated and not _chosen(issue, draft)]
        if draft.finished and not fresh and not unsettled:
            return {"jump_to": "end"}  # 끝내기를 불렀고 새 문제·다시 알릴 고칠 것이 없음: 모델을 다시 부르지 않음
        draft.finished = None  # 새 문제가 있거나 고칠 것이 남았으면 끝내기를 거두고 알림
        marked = [{**issue, "다시": True} if issue_key(issue) in self.reported else issue for issue in issues]
        self.repeated |= {issue_key(issue) for issue in issues if issue_key(issue) in self.reported}
        self.reported |= {issue_key(issue) for issue in issues}
        return {"messages": [HumanMessage(report(draft, marked))]}


def report(draft: Any, issues: list[dict[str, Any]]) -> str:
    counts = {section: len(draft.items.get(section, [])) for section in draft.sections}
    lines = ["# 검증 결과(프로그램이 지금 초안을 V1 결합·검증기로 본 것)", f"맡은 섹션 항목 수: {json.dumps(counts, ensure_ascii=False)}"]
    if not issues:
        lines.append("맡은 섹션에 남은 문제가 없습니다. 원문에서 빠뜨린 항목이 없으면 finish를 부릅니다.")
        return "\n".join(lines)
    # 섹션 전체에 걸친 문제(범위·기준표 누락 메모, 위치 「/quality/coverage/…」)를 항목별 문제보다 먼저: 항목 경고가 20개 가까우면 뒤에 붙은
    # 섹션 문제를 담당이 놓침(2026-11-07 유료 확인 jbdc-16011: 기준표 메모가 「확인할 것」 18개 속에 섞임)
    ordered = sorted(issues, key=lambda issue: not str(issue.get("target") or "").startswith("/quality/coverage/"))
    fix = [issue for issue in ordered if must_fix(issue)]
    check = [issue for issue in ordered if not must_fix(issue)]
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


def _chosen(issue: dict[str, Any], draft: Any) -> bool:
    """담당이 set_coverage(PARTIAL)로 직접 적은 섹션의 「범위 미완료」 계약 오류: 담당이 고른 상태라 끝내기를 돌려보내지 않음."""
    target = str(issue.get("target") or "")
    section = target.rsplit("/", 1)[-1]
    partial = (draft.coverage.get(section) or {}).get("status") == "PARTIAL"
    return issue.get("code") == "CONTRACT_INCOMPLETE_EXTRACTION" and target.startswith("/quality/coverage/") and partial


def issue_key(issue: dict[str, Any]) -> tuple[str, str, str]:
    """같은 문제인지: 코드·항목 id·항목 안 위치(항목을 빼면 목록 순번이 바뀌므로 순번은 빼고 셈)."""
    tokens = str(issue.get("target") or "").strip("/").split("/")
    inside = "/".join(tokens[2:]) if issue.get("item") and len(tokens) >= 2 and tokens[1].isdigit() else "/".join(tokens)
    return str(issue.get("code")), str(issue.get("item") or ""), inside
