"""제목으로 글 종류를 나눠요. 기관 게시판에는 모집공고 말고도 후속 안내·정정공고·기존 입주자 안내·매입 공고가 섞여 있어요.

결과
  NOTICE      모집공고 → 상세를 연다
  CORRECTION  정정공고 → 상세를 열고 원래 공고에 연결
  FOLLOW_UP   후속 안내(당첨자 발표, 서류제출 대상자 등) → 원래 모집공고가 있을 때만 열고 연결
  EXCLUDED    그 밖의 글 → 열지 않음
"""

import re
from dataclasses import dataclass
from datetime import date

NOTICE, CORRECTION, FOLLOW_UP, EXCLUDED = "NOTICE", "CORRECTION", "FOLLOW_UP", "EXCLUDED"
OPEN_KINDS = {NOTICE, CORRECTION}

FOLLOWUP = re.compile(
    r"당첨자|계약\s*대상자|계약\s*안내|서류\s*심사|심사\s*대상자|대상자\s*발표|입주\s*대상자|예비자\s*발표|면접|교육\s*이수"
    r"|접수\s*결과|접수\s*마감|주택\s*공개|커트라인|추첨\s*결과|동\s*·?\s*호\s*추첨|결과\s*발표|모집\s*결과|선정\s*결과"
    r"|계약\s*체결|서류\s*제출\s*대상|대상자\s*안내|신규\s*계약|접수\s*번호|입주\s*순번|순번\s*(?:추첨|결정)"
    # 인천·울산 실제 제목 (2026-10-20): 첨부 없는 선정·입주·일정 안내와 모집 종료·확정 알림.
    # '결과 공고'는 넣지 않아요: 산업단지 심사결과·동호배정 결과처럼 제외할 글까지 후속 안내로 바뀌어요
    r"|선정\s*(?:안내|발표)|입주\s*안내|일정\s*안내|모집\s*(?:종료|중단)|확정\s*공고|순번\s*결과|발표\s*지연"
)
EXISTING = re.compile(r"재계약|갱신\s*계약")  # 기존 입주자 안내
# 입주자 모집이 아닌 공고: 공사가 집을 사는 매입 공고, 사업자·운영자 공모, 토지·용지 공급, 보상, 평가위원
NOT_TENANT = re.compile(
    r"(?:기존\s*)?주택\s*매입\s*(?:재)?공고|매입\s*(?:재)?공고|사업자\s*(?:공모|모집)|택지|용지|수의\s*계약|낙찰"
    r"|보상\s*(?:계획|공고)|평가\s*위원|위원\s*(?:후보|모집|명단)"
    r"|운영자\s*(?:모집|공모|선정)|운영\s*기관\s*(?:모집|공모|선정)"  # 특화시설 운영자 모집 ('(운영기관 : ○○)'은 입주자 모집이라 제외 안 함)
)
BUSINESS_SPACE = re.compile(r"상가|점포|입점|사무실|창업|업무시설|근린생활|임차인")  # 이 수집기 범위 밖 (사업공간)
CORRECTION_MARK = re.compile(r"[\[(]\s*정정\s*(?:공고)?\s*[\])]|정정\s*공고")
RECRUIT = re.compile(r"모집\s*공고|입주자\s*모집|예비\s*입주자|추가\s*모집|잔여\s*세대.*모집")
REF = re.compile(r"(?P<name>.+?)\s*\(\s*(?:공고일?\s*:?\s*)?[‘'’]?(?P<y>\d{2,4})\s*[._]\s*(?P<m>\d{1,2})\s*[._]\s*(?P<d>\d{1,2})\s*\.?\s*(?:공고)?\s*\)")
# 후속 안내 단어 바로 뒤(같은 마디 안)의 바뀜 낱말: 「당첨자 발표일 변경」은 후속 안내가 아니라 무엇을 정정했는지예요
CHANGED = re.compile(r"[^,·\])]{0,12}?(?:변경|연기|연장|조정)")
QUALIFIER = re.compile(r"[\[(]([^\])]*)[\])]")


def out_of_scope(title: str) -> bool:
    """입주자 모집이 아닌 글(기존 입주자 안내, 매입·택지·보상 공고, 상가 등 사업공간).
    기관이 목록 머리말로 '모집공고'를 붙여도 이 제목이면 제외해요 (예: 대전 '기존주택(청년임대) 3차 매입공고')."""
    return bool(EXISTING.search(title) or NOT_TENANT.search(title) or BUSINESS_SPACE.search(title))


def classify(title: str) -> str:
    if out_of_scope(title):
        return EXCLUDED
    ref = REF.search(title)
    # 공고일 뒤의 정정 표시(「…모집공고(2026.10.01) 정정공고」)는 후속 안내 글이 아니에요(2026-11-10 코드 검토: 후속 안내로 분류됐음)
    after = CORRECTION_MARK.sub("", title[ref.end() :]) if ref else ""
    if ref and re.search(r"모집\s*공고", ref.group("name")) and len(re.sub(r"[^가-힣]", "", after)) >= 2:
        return FOLLOW_UP  # '…모집공고(2026. 6. 25.) 면접평가 대상자 발표'처럼 공고일 뒤에 글이 붙으면 후속 안내
    follow_ups = list(FOLLOWUP.finditer(title))
    if CORRECTION_MARK.search(title) and RECRUIT.search(title) and all(CHANGED.match(title, m.end()) for m in follow_ups):
        # 「[정정공고] … 모집공고(당첨자 발표일 변경)」: 후속 안내 단어가 바뀐 내용을 말할 뿐이면 정정공고예요.
        # 예전엔 후속 안내 검사가 먼저라 정정이 원래 공고에 반영되지 않았어요(2026-11-10 코드 검토)
        return CORRECTION
    if follow_ups:
        return FOLLOW_UP
    if RECRUIT.search(title):
        return NOTICE
    return EXCLUDED


def norm_name(text: str) -> str:
    """공고 이름 비교용: 꾸밈말([당첨자발표], (수요자맞춤형))과 '모집공고' 같은 공통 단어를 빼요."""
    text = re.sub(r"\[[^\]]*\]|\([^)]*\)", " ", text)
    text = re.sub(r"입주자|모집\s*공고문?|모집|공고|잔여\s*세대|예비|정정", " ", text)
    return re.sub(r"[^0-9A-Za-z가-힣]", "", text)


@dataclass(frozen=True)
class TitleRef:
    name: str
    posted_on: date


def title_ref(title: str) -> TitleRef | None:
    """후속 안내 제목 안의 '(2026. 8. 21.)' 같은 공고일과 그 앞의 공고명. 원래 모집공고를 찾는 데 써요."""
    found = REF.search(title)
    if not found:
        return None
    year = int(found.group("y"))
    year = year + 2000 if year < 100 else year
    try:
        return TitleRef(norm_name(found.group("name")), date(year, int(found.group("m")), int(found.group("d"))))
    except ValueError:
        return None


def same_notice(ref: TitleRef, title: str, posted_on: date | None) -> bool:
    """후속 안내가 가리키는 (공고명, 공고일)과 모집공고가 같은지."""
    own = norm_name(title)
    same_name = bool(ref.name and own) and (ref.name in own or own in ref.name)
    return same_name and posted_on == ref.posted_on


def correction_base(title: str) -> str:
    """정정공고를 원래 공고와 비교할 이름 (정정 표시를 뺀 공고명)."""
    return norm_name(CORRECTION_MARK.sub("", title))


def qualifiers(title: str) -> frozenset[str]:
    """괄호 안 구분 말(블록·단지·유형 등, 정정 표시는 뺌). norm_name은 이걸 지워서 따로 맞춰 봐요."""
    found = (re.sub(r"[^0-9A-Za-z가-힣]", "", q) for q in QUALIFIER.findall(CORRECTION_MARK.sub("", title)))
    return frozenset(q for q in found if q)


def same_qualifiers(a: frozenset[str], b: frozenset[str]) -> bool:
    """한쪽 구분 말이 다른 쪽에 모두 들어 있으면 같은 공고로 봐요(정정공고가 꾸밈말을 빼거나 더할 수 있음).
    「(A-2블록)」과 「(A-3블록)」처럼 서로 다른 구분이 있으면 다른 공고예요."""
    return a <= b or b <= a
