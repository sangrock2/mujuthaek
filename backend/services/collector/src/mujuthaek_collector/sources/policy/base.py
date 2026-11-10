"""정책 API 출처 규격. 게시판 수집기(sources/base.py)와 달리 화면이 아니라 공공 API 응답(JSON·XML)을 읽어요.

출처별로는 'API 주소를 어떻게 만들고, 받은 응답에서 무엇을 꺼내나'만 구현해요 (게시판 Source와 같은 모양).
  list_request·parse_list        목록 한 페이지 요청과 응답 → 정책 목록 + 전체 건수 (segments로 나눠 받을 수 있어요)
  detail_requests·parse_detail   상세(필요하면 여러 개) 요청과 응답 → 상세 항목
  parse_detail의 결과에 API가 주는 첨부(files)와, 첨부가 없을 때 열어볼 원문 주소(origin_urls)를 담아요.

페이지 넘기기, 1차 거름, 바뀐 정책 고르기, 원문 열기, 첨부 받기, 버전 비교, 저장, 이벤트는 policy/pipeline.py가 해요.
parse_* 함수는 네트워크를 모르는 순수 함수라 저장해 둔 응답으로 바로 테스트할 수 있어요.
"""

from __future__ import annotations

import hashlib
import json
import re
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any
from urllib.parse import urlencode

from lxml import etree

from mujuthaek_collector.core.files import FileRef
from mujuthaek_collector.errors import BlockedError, ParseError
from mujuthaek_collector.sources.base import Fetcher, Request

# 키 문제·호출 한도처럼 다시 시도해도 안 되는 API 오류. 그 출처의 이번 회차를 멈춰요 (BLOCKED)
BLOCKING_API_ERRORS = re.compile(r"SERVICE_KEY|SERVICE_ACCESS_DENIED|LIMITED_NUMBER|인증키|등록되지 않은|접근\s*거부", re.I)

# 1차 거름: 이주 혜택(주거·전입·정착) 단어가 이름·요약에 하나라도 있으면 상세를 열어요. 최종 판단은 AI 추출 단계가 해요.
# API의 분류(복지로 관심주제, 보조금24 서비스분야, 온통청년 대분류)는 쓰지 않아요. 2026-10-15 실제 값과 맞지 않았어요:
#   복지로 지자체 '주거' 태그 55건 중 주거 정책은 4건 (충남 청년 주택임차보증금 이자 지원은 '서민금융', 출산장려금·결식아동급식은 '주거')
#   보조금24 이 단어에 걸리는 881건 중 '주거·자립' 분야는 452건. '주거·자립' 580건 중 128건은 근로장려금·자산형성통장 등
# 걸리는 수: 보조금24 10,968건 중 약 880, 복지로 중앙 461건 중 약 45, 지자체 4,822건 중 약 480
# '인구감소'는 넣지 않아요. 출산장려금에 '인구감소 대응'이 많아서 40건이 더 걸려요.
SETTLE_WORDS = re.compile(
    r"주거|주택|임차|임대|전세|월세|보증금|전입|정주|이주|이사비|귀농|귀어|귀촌|빈집|집수리|인구\s*유입"
    r"|정착\s*(?:지원|금|비|장려|자금|수당)|(?:지역|농촌|어촌|산촌|청년|이주|전입|자립)\s*정착"  # '가족제도 정착'(효도수당) 같은 글은 빼요
)


def settle_related(*texts: Any) -> bool:
    return bool(SETTLE_WORDS.search(" ".join(str(t or "") for t in texts)))


# 창업지원 범위: 창업 공간 + 지원금·정책자금만 (2026-10-19 결정). 교육·멘토링·컨설팅·행사·경진대회·판로·홍보는 빼요.
# 출처 분류만으로는 섞여 있어서(K-Startup '시설ㆍ공간ㆍ보육'에 창업교육, '사업화'에 언론홍보) 이름의 단어도 같이 봐요.
#   1. 이름에 교육·행사 단어가 있고 공간 단어가 없으면 빼요 ('멘토링 입주기업 모집'은 남겨요)
#   2. 출처 분류가 공간·자금이거나, 이름(과 지원 내용)에 공간·자금 단어가 있으면 넣어요
# 2026-10-18 모집 중 기준: K-Startup 228 → 82, 기업마당 창업 179 → 90, 온통청년 중분류 창업 388 → 276
STARTUP_SPACE = re.compile(r"입주|입점|임대|임차|공간|오피스|사무실|보육\s*센터|인큐베이팅\s*센터|지식산업센터|창업\s*카페|메이커\s*스페이스|청년몰|점포|상가")
STARTUP_FUND = re.compile(
    r"지원금|자금|융자|보증|대출|이차\s*보전|바우처|사업화|창업\s*패키지|팁스|TIPS|사관학교|응원금|임차료|활동비|간접비|사업비|시제품"
    r"|\d[\d,.]*\s*(?:만|백만|천만|억)\s*원"  # '최대 20백만원', '1,200만 원'
)
STARTUP_EXCLUDE = re.compile(
    r"교육|특강|강의|강좌|아카데미|세미나|포럼|컨퍼런스|네트워킹|밋업|meet-?up|데모\s*데이|demo\s*day|(?<![A-Za-z])IR(?![A-Za-z])|피칭"
    r"|경진\s*대회|공모전|오디션|컨설팅|멘토링|멘티|클리닉|상담|코칭|캠프|간담회|설명회|교류회|박람회|전시회|홍보|해커톤|수강생|참관|대관"
    r"|수요\s*조사|통합\s*공고",
    re.I,
)


# 정책 분류 (raw_policies.field, 이벤트 field). 2026-10-22 결정: 지원 정책과 사업공간 모집을 나눠 따로 추출·저장해요.
#   BENEFIT            주거·이주 혜택 (보조금24, 복지로, 온통청년 주거)
#   STARTUP_SUPPORT    창업 지원금·정책자금, 창업 공간 임대료 지원
#   SPACE_RECRUITMENT  사업공간 모집: 창업 공간에 들어올 기업·팀을 뽑는 공고 (입주·입점 모집, 임대 공급)
BENEFIT, STARTUP_SUPPORT, SPACE_RECRUITMENT = "BENEFIT", "STARTUP_SUPPORT", "SPACE_RECRUITMENT"

# 사업공간 모집은 이름으로 나눠요. 공간을 빌려주지 않고 임대료를 대신 내주는 사업('창업 임대료 지원')은 STARTUP_SUPPORT예요.
# 2026-10-21 창업지원 DONE 287건 중 약 36건 (K-Startup 31: 창업보육센터·공유오피스 입주 모집, LH 업무시설 임대공급)
SPACE_RECRUIT = re.compile(r"입주(?:기업|자|팀|스타트업|기관)?.{0,6}모집|입점.{0,6}모집|임대\s*공급|입주.{0,4}공고|멤버십.{0,4}모집|입주ㆍ")


# 상가 모집은 수집하지 않아요 (2026-10-22 결정): 전통시장 청년몰·점포·상가·푸드존 부스에 들어올 상인을 뽑는 공고.
# 거름을 통과해도 SKIPPED로 두고, 사업공간 모집으로도 나누지 않아요. 점포 임차료 지원·상가 임대료 감면처럼 돈을 주는 사업은 그대로 수집해요.
#   예: 화성동탄2 … 스마트주차장 상가 임대공급, 김제전통시장 청년몰 입점 모집, 삼척중앙시장 청년몰 청년상인 수시모집,
#       금산금빛시장 청년몰 입점상인 모집, 백운광장 스트리트 푸드존 점포운영자 모집, 길음청년희망스토어 청년창업팀 모집, 순천시 청춘창고
SHOP_RECRUIT = re.compile(
    r"청년몰|청춘창고|청년\s*상인.{0,6}모집|입점\s*상인|점포\s*운영자"
    r"|(?:점포|상가|매장|스토어|청년식당).{0,15}(?:모집|입점|입주|임대\s*공급)"
)
SHOP_SUPPORT = re.compile(r"직매장|임차료|임대료|감면|안심벨|컨설팅|환경\s*개선")  # 상가 단어가 있어도 지원 사업


def shop_recruitment(title: Any) -> bool:
    name = str(title or "")
    return bool(SHOP_RECRUIT.search(name)) and not SHOP_SUPPORT.search(name)


# 온라인몰·판매전·판매관에 상품을 올릴 업체를 뽑는 「입점」은 공간을 빌려주지 않아서 사업공간 모집이 아니에요 (판로 지원, STARTUP_SUPPORT).
# 2026-10-26 기업마당 사업공간 모집 6건 중 6건: 김해온몰 입점기업, 북소e몰 입점 소상공인, K-SEAFOOD 판매 전용관 입점 제품,
#   인천국제공항 면세점 연계 수산식품 판매홍보관 입점업체, 김포시 우수제품 판매전 E-커머스 입점기업
ONLINE_SALES = re.compile(r"온라인|쇼핑몰|[eE]\s*몰|온몰|이커머스|[eE]-?\s*커머스|판매\s*전|판매\s*전용관|판매\s*홍보관|입점\s*제품")


def space_recruitment(title: Any) -> bool:
    name = str(title or "")
    return bool(SPACE_RECRUIT.search(name)) and not shop_recruitment(title) and not ONLINE_SALES.search(name)


def startup_in_scope(title: Any, text: Any = None, *, category_ok: bool = False) -> bool:
    """창업 공간·지원금·정책자금 공고인지. title은 공고·정책 이름, text는 지원 내용(이름만으로 모를 때), category_ok는 출처 분류가 공간·자금일 때."""
    name = str(title or "")
    if STARTUP_EXCLUDE.search(name) and not STARTUP_SPACE.search(name):
        return False
    words = f"{name} {text or ''}"
    return category_ok or bool(STARTUP_SPACE.search(words) or STARTUP_FUND.search(words))


@dataclass
class PolicyItem:
    policy_id: str  # 출처 안에서 유일 (raw_policies.policy_id)
    title: str
    marker: str  # 바뀌었는지 보는 값: 수정일, 없으면 목록 항목 해시
    record: dict[str, Any]  # 목록 응답 한 건 그대로

    def to_json(self) -> dict[str, Any]:
        """테스트·디버깅용. 저장할 때는 record를 raw_policies.list_raw에, marker를 marker 칸에 따로 넣어요."""
        return asdict(self)

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> PolicyItem:
        return cls(data["policy_id"], data["title"], data.get("marker", ""), data.get("record") or {})


@dataclass
class PolicyPage:
    items: list[PolicyItem]
    total: int | None  # 응답이 알려준 전체 건수 (모르면 None)
    # 응답에 온 항목 수 (ID가 없어 버린 항목 포함). 페이지 넘김은 이 값으로 판단해요.
    # items 수로 판단하면 꽉 찬 페이지에서 한 건만 버려도 마지막 페이지로 보고 다음 페이지를 읽지 않아요
    listed: int | None = None

    @property
    def count(self) -> int:
        return len(self.items) if self.listed is None else self.listed


NATIONWIDE, SIDO, SIGUNGU, UNKNOWN = "NATIONWIDE", "SIDO", "SIGUNGU", "UNKNOWN"
SCOPE_LABELS = {NATIONWIDE: "전국", SIDO: "시도", SIGUNGU: "시군구", UNKNOWN: "지역 모름"}


@dataclass
class PolicyDetail:
    record: dict[str, Any]  # 목록 + 상세 응답을 합친 항목 (raw_policy_versions.api_raw)
    files: list[FileRef] = field(default_factory=list)  # API가 알려준 첨부 (복지로 관련 서식)
    origin_urls: list[str] = field(default_factory=list)  # 첨부가 없을 때 열어볼 원문 공고 주소
    detail_url: str | None = None  # 사람이 열어볼 원문 주소 (이벤트의 detailUrl)
    apply_url: str | None = None
    agency: str | None = None
    region_scope: str = "UNKNOWN"  # NATIONWIDE 전국, SIDO 시도 전체, SIGUNGU 시군구, UNKNOWN 모름 (지방공기업 등)
    region_names: list[str] = field(default_factory=list)  # SIDO면 '부산광역시', SIGUNGU면 '경상북도 성주군'
    region_codes: list[str] = field(default_factory=list)  # 시군구 코드 5자리 (온통청년만 줘요)
    categories: list[str] = field(default_factory=list)  # 출처가 붙인 분야 (주거, 생활안정 …)
    modified_at: str | None = None  # 출처가 알려준 수정일 (형식은 출처마다 달라서 그대로)
    # 통일한 내용 칸 (raw_policy_versions). 출처에 없으면 None, 글로 오는 칸은 원문 그대로
    summary: str | None = None
    target: str | None = None  # 지원 대상
    criteria: str | None = None  # 선정 기준
    benefit: str | None = None  # 지원 내용
    how_to_apply: str | None = None  # 신청 방법
    apply_period: str | None = None  # 신청 기간·기한
    documents: str | None = None  # 제출 서류
    age_min: int | None = None  # API가 나이를 숫자로 줄 때만
    age_max: int | None = None


THIN_CHARS = 700  # WHEN_THIN: AI 입력 항목 글자(ai_text)가 이보다 짧으면 첨부를 봐요. 복지로 지자체 중앙값 약 570자 (2026-10-19)
SEE_NOTICE = re.compile(r"공고문?\s*(?:참조|참고|확인)|붙임\s*참조|첨부\s*(?:파일)?\s*(?:참조|참고)|별도\s*(?:공고|안내)|세부\s*내용은")


class PolicySource(ABC):
    code: str  # sources.code와 같아야 해요 (gov24, bokjiro_central, bokjiro_local, youth, kstartup, bizinfo)
    name: str
    provider: str  # 이벤트의 provider (GOV24, BOKJIRO, YOUTHCENTER, KSTARTUP, BIZINFO)
    field = BENEFIT  # 출처의 기본 분류. 창업지원 출처는 STARTUP_SUPPORT (정책마다 정하는 건 classify)
    page_size = 100
    weekly_recheck = False  # 목록에 수정일이 없는 출처는 주 1회 전부 다시 열어 상세·첨부가 바뀌었는지 봐요
    key_env = ""  # 인증키 환경 변수 이름 (README와 오류 안내에 써요)
    labels: dict[str, str] = {}  # 영문 항목 이름 → AI에 넘길 한글 이름
    # 내용 비교에서 빼는 항목: 매번 바뀌는 조회수, 그리고 수정일(다시 열어볼지 정하는 데만 써요. 수정일만 바뀌고 내용이 같으면 새 버전이 아니에요)
    volatile_keys: frozenset[str] = frozenset()
    # AI 입력(full_text)에 넣는 항목. 대상·선정기준·지원내용·신청방법·기간·요약 같은 설명 칸만 (비면 전체).
    # 주소·파일 경로·연락처·내부 코드·규칙으로 옮기는 코드 칸(온통청년 zipCd, 보조금24 지원조건 …)은 빼요.
    # 버전 비교(content_hash)는 body_text(전체 항목)로 해서, 빠진 칸이 바뀌어도 새 버전이 돼요
    ai_keys: tuple[str, ...] = ()
    # 첨부·원문 화면: ALWAYS 항상 찾아요, WHEN_THIN API 설명 칸이 짧거나 '공고문 참조'일 때만, NEVER 보지 않아요 (AI 비용·수집 시간)
    attachments = "ALWAYS"
    origin_files = True  # 원문 화면의 첨부 링크도 받을지. False면 본문 글자만 읽어요 (K-Startup: 첨부 경로가 robots.txt 금지)
    # 목록 항목의 등록일 칸 (앞에 있는 칸부터). 처음 수집 개수 제한에서 최신 순서와 기준일에 써요 (core/intake.py)
    listed_keys: tuple[str, ...] = ()

    def __init__(self, api_key: str | None):
        self.api_key = normalize_key(api_key)

    # ── 출처별로 구현 ──────────────────────────────────────────
    @abstractmethod
    def list_request(self, page: int, segment: str | None = None) -> Request: ...

    @abstractmethod
    def parse_list(self, body: str) -> PolicyPage:
        """목록 응답 → 정책 목록. 응답 모양이 다르면 ParseError, 키·한도 오류면 BlockedError."""

    @abstractmethod
    def parse_detail(self, item: PolicyItem, bodies: list[str]) -> PolicyDetail:
        """detail_requests 순서대로 받은 응답 → 상세."""

    # ── 필요할 때만 바꿈 ───────────────────────────────────────
    def segments(self) -> list[str | None]:
        """목록을 나눠 받을 단위 (온통청년은 정책 대분류마다). 기본은 한 번에 전체."""
        return [None]

    def detail_requests(self, item: PolicyItem) -> list[Request]:
        """상세를 받을 요청들. 목록 응답에 이미 다 있으면 빈 목록 (온통청년)."""
        return []

    def wanted(self, item: PolicyItem) -> bool:
        """목록 단계의 1차 거름. False면 상세를 열지 않고 SKIPPED로 남겨요.
        목록 항목은 그대로 저장해서, 기준을 넓히면 다음 회차에 목록을 다시 읽을 때 PENDING으로 돌아와요."""
        return True

    def closed(self, item: PolicyItem, today: date) -> bool:
        """신청이 끝난 정책인지. True면 wanted여도 SKIPPED로 남겨요 (AI 추출 비용을 아끼려고).
        SKIPPED도 회차마다 다시 판단해서, 기관이 새 신청 기간으로 고치면 PENDING으로 돌아와요."""
        return False

    def field_of(self, record: dict[str, Any]) -> str:
        """혜택인지 창업지원인지. 한 출처에 둘이 섞여 있으면 정책마다 정해요 (온통청년)."""
        return self.field

    def classify(self, title: Any, record: dict[str, Any]) -> str:
        """정책 분류 (raw_policies.field, 이벤트 field). 창업지원 중 이름이 입주·입점 모집, 임대 공급이면 사업공간 모집이에요.
        목록 단계(1차 거름)에서 정해 저장하고, 상세를 읽은 뒤 다시 정해요 (온통청년은 상세 없이 목록 항목으로 정해요)."""
        kind = self.field_of(record)
        return SPACE_RECRUITMENT if kind == STARTUP_SUPPORT and space_recruitment(title) else kind

    def prefetch(self, client: Fetcher, policy_ids: list[str]) -> None:
        """상세를 페이지로 한꺼번에 받을 수 있는 출처는 여기서 미리 받아 둬요 (보조금24).
        받아 둔 정책은 detail_requests가 빈 목록을 돌려주고 parse_detail이 받아 둔 값을 써요."""
        return None  # 기본: 정책마다 detail_requests로 받아요

    # ── 파이프라인이 부름 ─────────────────────────────────────
    def fetch_list(self, client: Fetcher, page: int, segment: str | None = None) -> PolicyPage:
        request = self.list_request(page, segment)
        return self.parse_list(client.text(request.url, data=request.data, referer=request.referer))

    def fetch_detail(self, client: Fetcher, item: PolicyItem) -> PolicyDetail:
        bodies = [client.text(r.url, data=r.data, referer=r.referer) for r in self.detail_requests(item)]
        return self.parse_detail(item, bodies)

    def secrets(self) -> list[str]:
        """오류 메시지·로그에서 가려야 하는 값."""
        return [self.api_key] if self.api_key else []

    def body_text(self, record: dict[str, Any]) -> str:
        """버전 비교와 AI 추출에 쓰는 항목 글자. 매번 바뀌는 항목(조회수)은 빼요."""
        lines = []
        for key, value in record.items():
            if key in self.volatile_keys or value in (None, "", [], {}):
                continue
            label = self.labels.get(key, key)
            if isinstance(value, (dict, list)):
                value = json.dumps(value, ensure_ascii=False, sort_keys=True)
            lines.append(f"{label}: {value}")
        return "\n".join(lines)

    def ai_text(self, record: dict[str, Any]) -> str:
        """AI 입력에 넣는 항목 글자: ai_keys 칸만, 그 순서로. 줄바꿈·공백을 정리해요 (복지로는 '\\r'로 줄을 나눠요)."""
        picked = {k: record[k] for k in self.ai_keys if k in record} if self.ai_keys else record
        text = self.body_text(picked).replace("\r\n", "\n").replace("\r", "\n")
        return re.sub(r"\n[ \t]*\n+", "\n", re.sub(r"[ \t]{2,}", " ", text)).strip()

    def needs_documents(self, record: dict[str, Any]) -> bool:
        """첨부·원문 화면을 볼지 (attachments)."""
        if self.attachments == "NEVER":
            return False
        if self.attachments == "WHEN_THIN":
            text = self.ai_text(record)
            return len(text) < THIN_CHARS or bool(SEE_NOTICE.search(text))
        return True

    def listed_on(self, record: dict[str, Any]) -> date | None:
        """목록 항목의 등록일. '2026-10-16 14:04:07'·'20261016'·'20220822150443' 모두 앞 8자리 숫자로 읽어요. 없거나 틀리면 None."""
        for key in self.listed_keys:
            digits = re.sub(r"\D", "", str(record.get(key) or ""))[:8]
            if len(digits) == 8:
                try:
                    return date(int(digits[:4]), int(digits[4:6]), int(digits[6:]))
                except ValueError:
                    continue
        return None

    def record_marker(self, record: dict[str, Any]) -> str:
        """수정일이 없는 출처는 목록 항목 해시로 바뀌었는지 봐요."""
        stable = {k: v for k, v in record.items() if k not in self.volatile_keys}
        return hashlib.sha256(json.dumps(stable, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:16]


# ── 공통 도우미 ────────────────────────────────────────────────
def normalize_key(key: str | None) -> str | None:
    """공공데이터포털은 인코딩 키(%2B …)와 디코딩 키를 둘 다 줘요. 주소에 넣을 때 한 번 인코딩하니까 디코딩 키로 맞춰요."""
    from urllib.parse import unquote

    if not key:
        return None
    key = key.strip()
    return unquote(key) if re.search(r"%[0-9A-Fa-f]{2}", key) else key


def build_url(base: str, params: dict[str, Any]) -> str:
    return f"{base}?{urlencode({k: v for k, v in params.items() if v not in (None, '')})}"


def clean(value: Any) -> Any:
    """문자열 앞뒤 공백 정리. 빈 문자열은 None으로."""
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


def load_json(body: str, what: str) -> Any:
    try:
        return json.loads(body)
    except ValueError as error:
        raise ParseError(f"{what} 응답이 JSON이 아니에요 (API 주소 변경 또는 점검 화면): {body[:120]!r}") from error


def raise_if_blocking(message: str) -> None:
    if BLOCKING_API_ERRORS.search(message):
        raise BlockedError(f"API가 요청을 거부했어요 (인증키·호출 한도 확인): {message}")


# ── XML (공공데이터포털 B554287 복지로 API) ────────────────────────
_XML_PARSER = etree.XMLParser(resolve_entities=False, no_network=True, recover=True, huge_tree=False)


def parse_xml(body: str, what: str) -> etree._Element:
    try:
        root = etree.fromstring(body.encode("utf-8"), parser=_XML_PARSER)
    except etree.XMLSyntaxError as error:
        raise ParseError(f"{what} 응답이 XML이 아니에요: {body[:120]!r}") from error
    if root is None:
        raise ParseError(f"{what} 응답이 비어 있어요")
    # 공공데이터포털 게이트웨이 오류: <OpenAPI_ServiceResponse><cmmMsgHeader><errMsg>…
    if root.tag == "OpenAPI_ServiceResponse" or root.find(".//cmmMsgHeader") is not None:
        message = " ".join(t for t in (root.findtext(".//errMsg"), root.findtext(".//returnAuthMsg"), root.findtext(".//returnReasonCode")) if t)
        raise_if_blocking(message)
        raise ParseError(f"{what} API 오류: {message}")
    code = (root.findtext(".//resultCode") or "").strip()
    if code and code not in ("0", "00", "000"):
        message = f"resultCode={code} {(root.findtext('.//resultMessage') or '').strip()}"
        raise_if_blocking(message)
        raise ParseError(f"{what} API 오류: {message}")
    return root


def xml_to_dict(element: etree._Element) -> dict[str, Any]:
    """하위 태그를 dict로. 같은 태그가 여러 번 나오거나 이름이 …List인 태그(basfrmList 등)는 목록이에요."""
    out: dict[str, Any] = {}
    for child in element:
        if not isinstance(child.tag, str):
            continue  # 주석
        value: Any = xml_to_dict(child) if len(child) else clean(child.text)
        if child.tag in out:
            if not isinstance(out[child.tag], list):
                out[child.tag] = [out[child.tag]]
            out[child.tag].append(value)
        elif child.tag.endswith("List") and len(child):
            out[child.tag] = [value]
        else:
            out[child.tag] = value
    return out


def as_list(value: Any) -> list[Any]:
    if value in (None, ""):
        return []
    return value if isinstance(value, list) else [value]


def split_names(value: Any) -> list[str]:
    """'주거, 생활지원' 같은 쉼표 구분 값을 목록으로. '주거·자립'처럼 가운뎃점은 이름의 일부라 나누지 않아요."""
    if not value:
        return []
    parts = value if isinstance(value, list) else re.split(r"[,|]", str(value))
    return [p.strip() for p in parts if p and str(p).strip()]


def int_or_none(value: Any) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None
