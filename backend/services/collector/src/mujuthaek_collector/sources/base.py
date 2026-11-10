"""출처 규격. 기관별 수집기는 '주소를 어떻게 만들고, 받은 화면에서 무엇을 꺼내나'만 구현해요.

페이지 넘기기, 멈추는 조건, 분류, 첨부 고르기·받기, 문서 추출, 버전 비교, 저장, 이벤트는 모두 pipeline.py가 해요.
parse_list·parse_detail은 네트워크를 모르는 순수 함수라서 저장해 둔 화면(tests/fixtures)으로 바로 테스트할 수 있어요.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any, Protocol

from mujuthaek_collector.core.files import FileRef


class Fetcher(Protocol):
    """요청 클라이언트 규격. 운영은 PoliteClient, 테스트는 FakeClient가 지켜요."""

    def text(self, url: str, *, data: dict[str, str] | None = None, referer: str | None = None) -> str: ...
    def download(self, url: str, *, referer: str | None = None) -> bytes: ...


@dataclass(frozen=True)
class Board:
    key: str  # raw_posts.board_key, source_boards.board_key (예: rent, sale, 43)
    name: str  # 사람이 읽는 이름 (임대, 분양 …)
    params: dict[str, str] = field(default_factory=dict)  # 목록 주소에 붙는 값


@dataclass(frozen=True)
class Request:
    url: str
    data: dict[str, str] | None = None  # 있으면 폼 POST
    referer: str | None = None


@dataclass
class ListItem:
    board: str
    post_key: str  # 출처 안에서 유일 (게시판이 여러 개면 접두어)
    title: str
    posted_on: date | None
    detail_url: str | None  # 사람이 열어볼 주소 (이벤트의 detailUrl)
    fetch_url: str | None = None  # 상세를 받을 주소 (없으면 detail_url). SH처럼 POST 전용이면 따로
    form: dict[str, str] | None = None  # 상세를 폼 POST로 받을 때 값
    referer: str | None = None
    list_status: str | None = None  # 목록의 상태 (접수중, 모집종료 …)
    deadline_on: date | None = None
    meta: dict[str, Any] = field(default_factory=dict)  # 목록에서 읽은 항목 (유형, 지역, 분류 …)
    files: list[FileRef] = field(default_factory=list)  # 목록에서 이미 아는 첨부 (경북·경남 JSON)

    def to_json(self) -> dict[str, Any]:
        """raw_posts.list_item에 그대로 저장해요. PENDING 글을 다음 회차에 다시 열 때 from_json으로 되살려요."""
        data = asdict(self)
        data["posted_on"] = self.posted_on.isoformat() if self.posted_on else None
        data["deadline_on"] = self.deadline_on.isoformat() if self.deadline_on else None
        return data

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> ListItem:
        values = dict(data)
        values["posted_on"] = date.fromisoformat(values["posted_on"]) if values.get("posted_on") else None
        values["deadline_on"] = date.fromisoformat(values["deadline_on"]) if values.get("deadline_on") else None
        values["files"] = [FileRef(**f) for f in values.get("files") or []]
        return cls(**values)


@dataclass
class Detail:
    title: str
    body_text: str
    files: list[FileRef]
    meta: dict[str, Any] = field(default_factory=dict)  # 상세 화면의 항목 (공고상태, 유형, 접수기간 …)
    posted_on: date | None = None
    region_code: str | None = None  # 시군구 코드 5자리. 수집 단계에서 알 때만 (LH: 마이홈 필지번호 앞 5자리)


class Source(ABC):
    code: str  # sources.code와 같아야 해요 (sh, gh, bmc, ih, dcco, dudc, umca, gbdc, gndc, soco, lh)
    name: str
    provider: str  # 이벤트의 provider (SH, GH, BMC …)
    boards: list[Board]
    legacy_tls = False  # 예전 보안 연결만 받는 기관
    prefer_doc = "pdf"  # 공고문 형식 우선순위

    # ── 기관별로 구현 ──────────────────────────────────────────
    @abstractmethod
    def list_request(self, board: Board, page: int) -> Request: ...

    @abstractmethod
    def parse_list(self, board: Board, body: str, page_url: str) -> list[ListItem]:
        """목록 화면 → 글 목록. 목록 표 자체를 못 찾으면 ParseError (글이 0개인 것과 구분)."""

    @abstractmethod
    def parse_detail(self, item: ListItem, body: str) -> Detail:
        """상세 화면 → 본문·항목·첨부. 본문 영역을 못 찾으면 ParseError."""

    # ── 필요할 때만 바꿈 ───────────────────────────────────────
    def make_client(self, settings: Any) -> Fetcher | None:
        """이 출처만의 요청 클라이언트가 필요할 때 돌려줘요 (LH: robots 예외 경로·API 간격). None이면 공통 PoliteClient."""
        return None

    def detail_request(self, item: ListItem) -> Request:
        return Request(item.fetch_url or item.detail_url or "", item.form, item.referer)

    def pre_classify(self, item: ListItem) -> str | None:
        """목록의 분류 칸으로 먼저 정할 수 있으면 종류(NOTICE·FOLLOW_UP·EXCLUDED …)를, 아니면 None(제목으로 분류)."""
        return None

    # ── 파이프라인이 부름 ─────────────────────────────────────
    def fetch_list(self, client: Fetcher, board: Board, page: int) -> list[ListItem]:
        request = self.list_request(board, page)
        body = client.text(request.url, data=request.data, referer=request.referer)
        return self.parse_list(board, body, request.url)

    def fetch_detail(self, client: Fetcher, item: ListItem) -> Detail:
        request = self.detail_request(item)
        body = client.text(request.url, data=request.data, referer=request.referer)
        return self.parse_detail(item, body)
