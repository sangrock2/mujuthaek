"""판정 틀 가공의 공통 부분: ID, 조건 공통 칸, 검수 사유, 원문 질문(ASK), 안내(note), 기준일, 신분 코드."""

from __future__ import annotations

import copy
import re
from datetime import date
from typing import Any

from mujuthaek_extraction.contracts import tools

# 주거 틀의 신분 코드(계층 이름·신분 정의 문장 → 코드). 사업공간 틀의 유형 코드는 business_space.STATUS_WORDS
STATUS_WORDS = (
    (re.compile(r"생계(?:\s*급여)?"), "LIVELIHOOD_BENEFIT"),
    (re.compile(r"의료(?:\s*급여)?"), "MEDICAL_BENEFIT"),
    (re.compile(r"주거\s*급여"), "HOUSING_BENEFIT"),
    (re.compile(r"교육\s*급여"), "EDUCATION_BENEFIT"),
    (re.compile(r"차상위(?:\s*계층)?"), "NEAR_POOR"),
    (re.compile(r"한\s*부모(?:\s*가족)?"), "SINGLE_PARENT"),
    (re.compile(r"장애인"), "DISABLED"),
    (re.compile(r"국가\s*유공자|보훈\s*대상자?"), "NATIONAL_MERIT"),
    (re.compile(r"북한\s*이탈\s*주민"), "NORTH_KOREAN_DEFECTOR"),
    (re.compile(r"보호\s*종료\s*아동|시설\s*퇴소자|자립\s*준비\s*청년"), "FACILITY_LEAVER"),
    (re.compile(r"대학생"), "UNIVERSITY_STUDENT"),
    (re.compile(r"취업\s*준비생"), "JOB_SEEKER"),
)
STATUS_FILLER = re.compile(r"수급(?:권)?자|계층|가구|가족|대상자|기업|[·,/및\s()]")
BONUS_WORDS = re.compile(r"[1-9]\s*인\s*(?:가구)?\s*\(?\s*\d+\s*%|맞벌이|가산|신생아|출생\s*자녀")
# 「청약할 수 없습니다」「입주자로 선정될 수 없습니다」도 제한(실측 2026-10-21 김해 매각·든든전세가 방향 모르는 질문으로 나감)
# 「부적격자로 처리됩니다」「탈락처리 됨」「지원받을 수 없으며」「공동명의 … 불허」도 제한(2026-10-22 방향 미정 959건 분류)
# 「불가피한 사유」는 제한이 아니고(리뷰 2026-10-22), 「…를 제외하고는·제외한」은 자격 문장을 꾸미는 말이라 따로 봅니다(EXCEPT_MODIFIER)
LIMIT_WORDS = re.compile(
    r"불가(?!피)(?:합니다|함|능)?|(?:신청|청약|선정|공급)\S*\s*(?:할|될|받을)\s*수\s*없|제외(?!\s*(?:한|하고|하면|된))|무효|안\s*됩니다"
    r"|부적격|탈락\s*처리|지원\s*받을\s*수\s*없|불허"
)
PERMIT_WORDS = re.compile(r"(?:신청|청약)\s*(?:이\s*)?가능|(?:신청|청약)할\s*수\s*있|(?:도|이상도)\s*가능")
NOT_REQUIRED = re.compile(r"불문|따지지\s*않|묻지\s*않|검증하지\s*않|적용(?:되|하)지\s*않|제한하지\s*않|관계\s*없")
REQUIRE_END = re.compile(r"(?:것|자|자로서|사람|세대|경우|에게\s*공급합니다)\s*[.)]?$")
# 자격 문장의 다른 끝(2026-10-22 방향 미정 959건 분류): 대상을 가리키는 명사(「…성년자인 무주택세대구성원(주민등록표등본 기준)」
# 「…자녀가 있는 가구」)와 「…을 갖추어야 합니다」「…무주택이어야 합니다」 같은 요구. 끝의 괄호 부연은 빼고 봅니다
PERSON_END = re.compile(r"(?:구성원|성년자|가구|부부|가족)\s*\.?$")
MUST_END = re.compile(r"(?:어|여|해|이어)\s*야\s*(?:합니다|함|한다)\s*\.?$")
# 요구 끝이라도 「…경우에는 … 상환하여야 함」처럼 조건이 붙은 문장은 자격인지 정하지 않습니다
CONDITIONAL = re.compile(r"경우|때에?는|시에는|되면|이후라도")
# 「만 65세 이상인 경우를 제외하고는 무주택이어야 합니다」「공공임대주택 입주자를 제외한 무주택세대구성원」: 제외 대상이 딸린 자격 문장
EXCEPT_MODIFIER = re.compile(r"제외\s*(?:한|하고|하면|된)")
TAIL_ASIDE = re.compile(r"(?:\s*(?:\([^)]*\)|\[[^\]]*\]|（[^）]*）|【[^】]*】))+\s*\.?$")
# 괄호·대괄호 안 부연(「[외국인 청약불가]」「(LH 임직원 제외)」): 문장의 주된 뜻(자격인지 제한인지)을 정할 때는 빼고 봅니다
ASIDE = re.compile(r"\[[^\]]*\]|\([^)]*\)|（[^）]*）|【[^】]*】")
QUALIFY_WORDS = re.compile(r"자격|요건|갖춘|충족|해당하는\s*(?:자|사람|분)|에게\s*공급")


class Context:
    """후보 한 건의 가공 상태: 쓴 ID, 검수 사유를 찾을 이슈·보류."""

    def __init__(self, candidate: dict[str, Any], regions: Any = None, *, approved: bool = False):
        """approved: 검수자가 승인한 결과. 사람이 이슈·보류까지 확인했으므로 추출 검수 사유로는 inReview를 붙이지 않습니다
        (틀 자체의 사유 — 가산을 못 읽음, 조건식을 옮길 수 없음 등 — 은 그대로 남습니다)."""
        self.candidate = candidate
        self.regions = regions
        self.used: set[str] = set()
        quality = candidate["quality"]
        self.issues = [] if approved else [(i["target"], i["code"]) for i in quality.get("reviewIssues") or []]
        self.held = [] if approved else quality.get("heldItems") or []
        self.approved = approved
        self.groups = 0

    def new_id(self, base: str) -> str:
        base = re.sub(r"\s+", "-", str(base).strip()) or "c"
        name, n = base, 1
        while name in self.used:
            n += 1
            name = f"{base}-{n}"
        self.used.add(name)
        return name

    def copy(self, criterion: dict[str, Any], suffix: str) -> dict[str, Any]:
        """여러 대상군에 같은 조건을 넣을 때 ID만 바꾼 사본(ANY_OF 안 조건까지)."""
        made = copy.deepcopy(criterion)

        def rename(node: dict[str, Any]) -> None:
            node["id"] = self.new_id(f"{node['id']}-{suffix}")
            for option in node.get("options") or []:
                for inner in option["criteria"]:
                    rename(inner)

        rename(made)
        return made

    def review_reasons(self, index: int, item: dict[str, Any]) -> list[str]:
        """추출이 이 자격 항목을 확신하지 못한 이유(검수 이슈·보류·예외). publish.conditions와 같은 기준에 예외 유무를 더합니다."""
        pointer = f"/eligibility/{index}"
        codes = {code for target, code in self.issues if target == pointer or target.startswith(pointer + "/")}
        codes |= {code for h in self.held if tools().overlaps_held(pointer, [h["target"]]) for code in h["codes"]}
        reasons = [f"추출 검수 사유: {', '.join(sorted(codes))}"] if codes else []
        if item.get("exceptionsStatus") == "NOT_REVIEWED" and not self.approved:
            reasons.append("예외 문구를 확인하지 않았습니다")
        return reasons

    def flag(self, criterion: dict[str, Any], reasons: list[str]) -> None:
        if not reasons:
            return
        criterion["inReview"] = True
        before = criterion.get("reviewReason")
        criterion["reviewReason"] = "; ".join(dict.fromkeys([*([before] if before else []), *reasons]))

    def quoted(self, pattern: str) -> bool:
        """후보의 원문 근거 인용 어딘가에 pattern이 있는지(설명 문장의 값을 원문으로 확인할 때)."""
        return any(re.search(pattern, e.get("quote") or "") for e in self.candidate.get("evidence") or [])

    def mentions_bonus(self, item: dict[str, Any]) -> bool:
        """같은 대상의 소득 항목 어딘가에 가산 낱말이 있는지(그 항목 원문에서 못 읽었으면 가산이 빠졌을 수 있음)."""
        mine = set(item["scope"].get("targetGroups") or [])
        for other in self.candidate["eligibility"]:
            words = f"{other.get('originalText') or ''} {other.get('description') or ''}"
            # 소득 항목이 아니어도 「가산 적용 : 출산자녀 … 20% 가산」처럼 가산만 따로 적은 문장이면 봅니다(실측 광주선운2)
            if other.get("category") != "INCOME" and not re.search(r"가산[^.]{0,40}?\d+\s*%|\d+\s*%\s*p?\s*가산", words):
                continue
            theirs = set(other["scope"].get("targetGroups") or [])
            if mine and theirs and not (mine & theirs):
                continue
            if BONUS_WORDS.search(f"{other.get('originalText') or ''} {other.get('description') or ''}"):
                return True
        return False


def base_fields(new_id: str, kind: str, quote: str | None) -> dict[str, Any]:
    return {"id": new_id, "kind": kind, "quote": quote or None, "page": None, "inReview": False, "reviewReason": None}


def group_id(ctx: Context, name: str) -> str:
    ctx.groups += 1
    return ctx.new_id(f"group-{ctx.groups}")


def ask(ctx: Context, item: dict[str, Any], reasons: list[str]) -> dict[str, Any]:
    """원문 문장을 그대로 묻는 질문. 신청 제한 문장이면 「해당하면 안 됨(metWhen NO)」, 자격 문장이면 「갖추면 됨(YES)」.
    둘 중 무엇인지 정할 수 없으면 YES로 두고 inReview입니다."""
    text = (item.get("originalText") or item.get("description") or "").strip()
    criterion = base_fields(ctx.new_id(item["id"]), "ASK", item.get("originalText"))
    core = ASIDE.sub(" ", text).strip()
    if LIMIT_WORDS.search(core):
        criterion |= {"question": f"다음 신청 제한에 해당하나요? 「{text}」", "metWhen": "NO"}
        if QUALIFY_WORDS.search(core) or REQUIRE_END.search(core):
            # 「…성년자는 신청 가능하며 외국인은 불가」처럼 자격과 제한이 한 문장에 섞이면 어느 쪽으로 물어도 틀릴 수 있습니다
            reasons = [*reasons, "자격과 신청 제한이 한 문장에 섞여 있어 질문 방향을 코드로 정하지 못했습니다"]
    else:
        criterion |= {"question": f"다음 자격을 갖추었나요? 「{text}」", "metWhen": "YES"}
        if LIMIT_WORDS.search(text):
            # 제한 문구가 괄호 안에만 있음(실측 2026-10-21 부산: 「…거주하는 무주택세대구성원인 성년자 [외국인 청약불가]」를
            # 「신청 제한에 해당하나요?」로 물어 자격을 갖춘 사람이 떨어지게 됨)
            reasons = [*reasons, "괄호 안에 신청 제한 문구가 있어 질문 하나로 자격과 제한을 함께 확인할 수 없습니다"]
        elif EXCEPT_MODIFIER.search(core):
            # 자격 문장에 제외 대상이 딸림: 갖추면 됨(YES)으로 묻되 제외 대상은 질문 하나로 확인할 수 없어 확인 필요(리뷰 2026-10-22)
            reasons = [*reasons, "자격 문장에 제외 대상이 함께 있어 원문 확인이 필요합니다"]
        elif not _qualification(text):
            reasons = [*reasons, "원문 문장이 자격인지 신청 제한인지 코드로 정하지 못했습니다"]
    ctx.flag(criterion, reasons)
    return criterion


def _qualification(text: str) -> bool:
    """제한 문구가 없는 문장이 자격(갖추면 됨)으로 끝나는지. 머리글만 있는 짧은 문장(「세대구성원(자격검증대상)」)과
    「단, …」로 시작하는 덧붙임은 정하지 않습니다."""
    end = TAIL_ASIDE.sub("", text).strip()
    if len(end) < 10 or re.match(r"^[※*\-•·▪◾\s]*단\s*[,.]?\s", end):
        return False
    if end != text and re.search(r"경우\s*\.?$", end):
        return False  # 「…외국인인 경우(…)」: 괄호를 떼면 「경우」로 끝나지만 문장이 이어지다 잘린 것
    if REQUIRE_END.search(end) or PERSON_END.search(end):
        return True
    return bool(MUST_END.search(end)) and not CONDITIONAL.search(end)


def ask_whole(ctx: Context, item: dict[str, Any], quote: str | None, reason: str) -> dict[str, Any]:
    """틀의 칸으로 정확히 담을 수 없는 조건: 원문 전체를 질문으로 두고 확인 필요(2026-10-21 리뷰: 담을 수 있는 부분만 떼어 내면 뜻이 바뀜)."""
    text = (item.get("originalText") or quote or "").strip()
    criterion = base_fields(ctx.new_id(item["id"]), "ASK", item.get("originalText") or quote)
    criterion |= {"question": f"다음 조건에 해당하나요? 「{text}」", "metWhen": "YES"}
    ctx.flag(criterion, [reason])
    return criterion


def note(kind: str, text: str, quote: str | None) -> dict[str, Any]:
    return {"kind": kind, "groupId": None, "text": text, "quote": quote or None, "page": None}


def unsure(candidate: dict[str, Any], pointer: str, *, approved: bool = False) -> bool:
    """그 위치가 보류됐거나 검수 이슈가 걸려 확정 값이 아닌지. 승인한 결과는 사람이 확인했으므로 늘 확정입니다."""
    if approved:
        return False
    quality = candidate["quality"]
    targets = [str(i["target"]).split(" ", 1)[0] for i in quality.get("reviewIssues") or []]
    targets += [h["target"] for h in quality.get("heldItems") or []]
    return tools().overlaps_held(pointer, targets)


def reference_date(candidate: dict[str, Any], *, approved: bool = False) -> date | None:
    """판정 기준일: 공고일(일정의 공고일, 없으면 공고 기본 정보의 공고일). 보류되거나 검수 이슈가 걸린 날짜는 쓰지 않습니다
    (2026-10-21 검토: API와 다른 공고일을 보류해도 그 날짜가 기준일이 되어 소득 기준 연도까지 틀림). 쓸 날짜가 없으면 None(틀 없음)."""
    for s, schedule in enumerate(candidate.get("schedules") or []):
        if "ANNOUNCEMENT" in (schedule.get("kinds") or []):
            for end in ("startsAt", "endsAt"):
                value = _day(schedule.get(end))
                if value and not unsure(candidate, f"/schedules/{s}/{end}", approved=approved):
                    return value
    if unsure(candidate, "/notice/announcedOn", approved=approved):
        return None
    return _day(candidate["notice"].get("announcedOn"))


def _day(value: Any) -> date | None:
    if isinstance(value, dict):
        value = value.get("value")
    if isinstance(value, str) and re.match(r"\d{4}-\d{2}-\d{2}", value):
        return date.fromisoformat(value[:10])
    return None


BENEFIT_LIST = re.compile(r"(?:생계|주거|의료|교육)(?:[\s·,ㆍ․‧]*(?:생계|주거|의료|교육))*\s*급여")
BENEFIT_CODES = {"생계": "LIVELIHOOD_BENEFIT", "의료": "MEDICAL_BENEFIT", "주거": "HOUSING_BENEFIT", "교육": "EDUCATION_BENEFIT"}


def status_codes(text: str, words: tuple[tuple[re.Pattern[str], str], ...]) -> list[str]:
    """문장에 나오는 신분 코드(words가 가진 코드만). 「생계·주거·의료·교육급여」처럼 급여를 묶어 적은 것도 읽습니다."""
    allowed = {code for _, code in words}
    codes = [BENEFIT_CODES[w] for m in BENEFIT_LIST.finditer(text) for w in re.findall(r"생계|주거|의료|교육", m.group(0))]
    codes = [c for c in codes if c in allowed]
    rest = BENEFIT_LIST.sub(" ", text)
    codes += [code for pattern, code in words if code not in BENEFIT_CODES.values() and pattern.search(rest)]
    return list(dict.fromkeys(codes))


def status_rest(text: str, words: tuple[tuple[re.Pattern[str], str], ...]) -> str:
    """신분 낱말·이어 주는 말을 뺀 나머지(비면 문장 전체가 신분)."""
    rest = BENEFIT_LIST.sub(" ", text)
    for pattern, _ in words:
        rest = pattern.sub(" ", rest)
    return STATUS_FILLER.sub("", rest)


def statuses_of(name: str, words: tuple[tuple[re.Pattern[str], str], ...]) -> list[str]:
    """대상 이름의 모든 낱말이 신분이면 그 신분 코드들, 아니면 빈 목록."""
    codes, rest = [], name
    for pattern, code in words:
        if pattern.search(rest):
            codes.append(code)
            rest = pattern.sub(" ", rest)
    return codes if codes and not STATUS_FILLER.sub("", rest) else []
