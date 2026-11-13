"""정책 수집 전체 흐름: 실제 출처 파서 + 가짜 클라이언트 + 메모리 저장소. 기관 사이트·API에는 요청하지 않아요."""

import json
from dataclasses import replace
from datetime import date

import httpx
import pytest

from mujuthaek_collector.core.storage import MAX_ATTEMPTS
from mujuthaek_collector.errors import BlockedError
from mujuthaek_collector.sources.policy import gov24, pipeline
from mujuthaek_collector.sources.policy.base import PolicyItem, build_url
from mujuthaek_collector.sources.policy.bizinfo import BizinfoSource
from mujuthaek_collector.sources.policy.bokjiro import BOKJIRO_VIEW, BokjiroCentralSource, BokjiroLocalSource
from mujuthaek_collector.sources.policy.config import PolicySettings
from mujuthaek_collector.sources.policy.event import build_policy_event
from mujuthaek_collector.sources.policy.gov24 import Gov24Source
from mujuthaek_collector.sources.policy.kstartup import KStartupSource
from mujuthaek_collector.sources.policy.youth import YouthSource
from mujuthaek_platform.contracts import validate_event
from tests import policy_samples as s
from tests.fakes import FakeClient
from tests.policy_fakes import PolicyMemoryStore, detail_urls, list_url

TODAY = date(2026, 10, 15)
KEY = "SeCrEt+Key/=="
PDF = b"%PDF-1.4 fake"
HWP = b"\xd0\xcf\x11\xe0" + b"HWP Document File" + b"\x00" * 64


@pytest.fixture
def policy_store():
    return PolicyMemoryStore()


@pytest.fixture
def api():
    return FakeClient()


@pytest.fixture
def web():
    return FakeClient()


@pytest.fixture
def policy_settings():
    return PolicySettings(data_go_kr_key=KEY, youth_key=KEY, detail_limit=20, api_delay_seconds=0)


@pytest.fixture(autouse=True)
def fake_text(monkeypatch):
    """첨부 글자 뽑기는 문서 모듈 테스트가 따로 해요. 여기서는 형식별로 정해진 글자를 돌려줘요."""
    monkeypatch.setattr(pipeline, "extract_text", lambda data, ext: (f"{ext} 문서 글자 " * 30, f"{ext.upper()} 텍스트"))


def run(source, api, web, store, file_store, settings, **kwargs):
    return pipeline.run_policy_source(source, api, web, store, file_store, settings, today=TODAY, **kwargs)


def central(api, web, detail=s.BOKJIRO_CENTRAL_DETAIL, attachments="ALWAYS"):
    source = BokjiroCentralSource(KEY)
    source.attachments = attachments  # 첨부 흐름 테스트용. 실제 복지로 중앙은 NEVER (test_bokjiro_central_skips_documents)
    api.pages[list_url(source, 1)] = s.BOKJIRO_CENTRAL_LIST
    api.pages[detail_urls(source, source.parse_list(s.BOKJIRO_CENTRAL_LIST).items[0])[0]] = detail
    web.files["https://www.bokjiro.go.kr/files/form/청년전세임대_안내문.pdf"] = PDF
    web.files["https://www.bokjiro.go.kr/files/form/download.do?id=77"] = HWP
    return source


def youth(api, web, policy=s.YOUTH_POLICY, page=s.ORIGIN_PAGE):
    source = YouthSource(KEY, ["주거"])
    api.pages[list_url(source, 1, "주거")] = s.youth_list([policy])
    web.pages["https://www.incheon.go.kr/board/view.do?id=3301"] = page
    web.files["https://www.incheon.go.kr/cmm/fms/FileDown.do?atchFileId=F1&fileSn=0"] = HWP
    web.files["https://www.incheon.go.kr/cmm/fms/FileDown.do?atchFileId=F1&fileSn=1"] = HWP + b"form"
    return source


def test_api_files_are_saved_with_event(api, web, policy_store, file_store, policy_settings):
    result = run(central(api, web), api, web, policy_store, file_store, policy_settings)
    assert result.status == "SUCCESS" and result.new_count == 1
    post = policy_store.by_key("WLF00001188")
    assert post.status == "DONE" and post.source_code == "bokjiro_central"
    version = policy_store.versions[0]
    assert version.api_raw["tgtrDtlCn"] == "무주택 청년(만 19~39세)" and version.origin_checked == []
    assert [(f.name, f.role) for f in version.files] == [("청년전세임대 안내문.pdf", "POLICY_DOC")]
    assert "https://www.bokjiro.go.kr/files/form/download.do?id=77" not in web.requested  # 신청서는 받지 않아요
    assert "[API 첨부: 청년전세임대 안내문.pdf]" in version.full_text and "pdf 문서 글자" in version.full_text
    assert not web.pages  # API가 첨부를 줘서 원문 화면은 열지 않았어요
    event = policy_store.events[0]
    validate_event(event)
    assert event["eventType"] == "raw.policy.collected" and event["payload"]["files"][0]["foundOn"] == "API"
    assert event["payload"]["record"]["servId"] == "WLF00001188" and event["payload"]["categories"] == ["주거", "생활지원"]
    assert event["payload"]["hasDocument"] is True and event["payload"]["hasOriginText"] is False
    assert any(k.startswith("raw/bokjiro_central/WLF00001188/v1/00-") for k in file_store.objects)


def test_bizinfo_print_file_is_main_document(api, web, policy_store, file_store, policy_settings):
    source = BizinfoSource(KEY)
    api.pages[list_url(source)] = s.bizinfo_list([s.BIZINFO_STARTUP, s.BIZINFO_SME])
    detail = source.parse_detail(source.parse_list(api.pages[list_url(source)]).items[0], [])
    web.files[detail.files[0].url] = PDF
    web.files[detail.files[1].url] = HWP
    web.files[detail.files[2].url] = HWP + b"hwpx"
    result = run(source, api, web, policy_store, file_store, policy_settings)
    assert result.status == "SUCCESS" and result.new_count == 1
    assert policy_store.by_key("PBLN_000000000127291").status == "SKIPPED"  # 창업 공고가 아님
    version = policy_store.versions[0]
    assert [(f.name, f.role) for f in version.files] == [("2026년 청년농업인 기술창업 지원사업 공고문.pdf", "POLICY_DOC")]
    assert detail.files[1].url not in web.requested  # 참가 신청서는 받지 않아요
    assert detail.files[2].url not in web.requested  # 공고문 글자를 하나 뽑으면 더 받지 않아요 (MAX_TEXT_DOCS)
    assert version.fields.field == "STARTUP_SUPPORT" and version.document_status == "OK" and version.origin_status == "NOT_OPENED"
    assert "[API 첨부: 2026년 청년농업인 기술창업 지원사업 공고문.pdf]" in version.full_text and "<p>" not in version.full_text
    event = policy_store.events[0]
    validate_event(event)
    assert (event["payload"]["sourceCode"], event["payload"]["provider"], event["payload"]["field"]) == ("bizinfo", "BIZINFO", "STARTUP_SUPPORT")
    sent = event["payload"]["files"][0]  # extraction이 S3에서 원본을 가져갈 위치와 형식
    assert (sent["fileType"], sent["role"]) == ("pdf", "POLICY_DOC")
    assert sent["s3Key"] == version.files[0].s3_key and sent["s3Key"].startswith("raw/bizinfo/") and sent["s3Key"] in file_store.objects
    assert not any(KEY in w for w in result.warnings)


def test_nul_in_document_text_is_removed(api, web, policy_store, file_store, policy_settings, monkeypatch):
    monkeypatch.setattr(pipeline, "extract_text", lambda data, ext: ("공고\x00 본문 " * 30, "HWP 텍스트"))
    run(central(api, web), api, web, policy_store, file_store, policy_settings)
    version = policy_store.versions[0]
    assert "\x00" not in version.full_text and all("\x00" not in (f.text or "") for f in version.files)


def test_kstartup_uses_list_only(api, web, policy_store, file_store, policy_settings):
    source = KStartupSource(KEY)
    api.pages[list_url(source)] = s.kstartup_list([s.KSTARTUP_POLICY])
    result = run(source, api, web, policy_store, file_store, policy_settings)
    assert result.status == "SUCCESS" and result.new_count == 1
    assert api.requested == [list_url(source)] and web.requested == []  # 상세 API도 상세 화면도 열지 않아요
    version = policy_store.versions[0]
    assert version.document_status == "NO_SOURCE" and version.origin_status == "NO_SOURCE"
    assert "지원사업 공고명: [ 모 집 ] GVC AI Platform & Startup Enabling Program" in version.full_text
    event = policy_store.events[0]
    validate_event(event)
    assert (event["payload"]["provider"], event["payload"]["field"], event["payload"]["policyId"]) == ("KSTARTUP", "STARTUP_SUPPORT", "179540")

    again = run(source, api, web, policy_store, file_store, policy_settings)  # 같은 목록이면 다시 열지 않아요
    assert again.new_count == 0 and len(policy_store.versions) == 1


def kstartup_page(title: str) -> str:
    """K-Startup 상세 화면 모양 (본문의 '입주공간 및 이용료'). 첨부 링크는 /afile/이라 받지 않아요."""
    return (
        f"<html><body><div id='contents'><h3>{title}</h3><div class='box'>"
        "<p>우수한 기술력을 보유하고 성장성이 유망한 서울시 기술 창업기업을 지원하기 위해 신규 입주기업 모집을 아래와 같이 진행합니다.</p>"
        "<p>입주공간 및 이용료 1. 소재지: 서울시 동작구 노량진로10, 서울창업센터 동작 (대방역 2번 출구) "
        "2. 모집공간: 3인실(18㎡) 1개, 5인실(24㎡) 7개, 12인실(47㎡) 1개 3. 입주비용: ㎡당 이용료 3,660원 (VAT 미포함) "
        "4. 모집대상: 모집공고일 기준 창업 7년 이내 스타트업 5. 모집규모: 총 10개사 내외 "
        "6. 입주기간: 24개월 (연장평가 결과에 따라 1년 단위로 최대 2회 연장 가능)</p>"
        "<p>선정절차 및 평가방법: 서류 평가 후 발표 평가로 선정하며, 세부 내용은 공고문을 참조하시기 바랍니다.</p>"
        "</div><a href='/afile/fileDownload/iN1Ln' title='[첨부파일] 공고문.pdf'>공고문.pdf</a></div></body></html>"
    )


def test_space_recruitment_is_classified_at_list_and_sent_with_its_field(api, web, policy_store, file_store, policy_settings):
    source = KStartupSource(KEY)
    space = {**s.KSTARTUP_POLICY, "pbanc_sn": "179600", "biz_pbanc_nm": "2026년 서울창업센터 동작 입주기업 모집", "supt_biz_clsfc": "시설ㆍ공간ㆍ보육"}
    api.pages[list_url(source)] = s.kstartup_list([s.KSTARTUP_POLICY, space])
    policy_settings = replace(policy_settings, detail_limit=0)  # 목록만 읽어요
    run(source, api, web, policy_store, file_store, policy_settings)
    assert policy_store.by_key("179600").field == "SPACE_RECRUITMENT" and policy_store.by_key("179540").field == "STARTUP_SUPPORT"

    web.pages[space["detl_pg_url"]] = kstartup_page(space["biz_pbanc_nm"])  # 사업공간 모집은 상세 화면 본문을 읽어요
    run(source, api, web, policy_store, file_store, replace(policy_settings, detail_limit=10))
    for event in policy_store.events:
        validate_event(event)
    fields = {e["payload"]["policyId"]: e["payload"]["field"] for e in policy_store.events}
    assert fields == {"179540": "STARTUP_SUPPORT", "179600": "SPACE_RECRUITMENT"}
    assert policy_store.by_key("179600").field == "SPACE_RECRUITMENT"


def test_shop_recruitment_is_skipped(api, web, policy_store, file_store, policy_settings):
    """상가 모집(청년몰·상가 임대공급)은 수집하지 않아요. 점포 임차료 지원처럼 돈을 주는 사업은 그대로 수집해요."""
    source = KStartupSource(KEY)
    rows = [
        {**s.KSTARTUP_POLICY, "pbanc_sn": "1", "biz_pbanc_nm": "화성동탄2 인큐베이팅센터 및 스마트주차장 상가 임대공급", "supt_biz_clsfc": "시설ㆍ공간ㆍ보육"},
        {**s.KSTARTUP_POLICY, "pbanc_sn": "2", "biz_pbanc_nm": "김제전통시장 청년몰 입점 모집", "supt_biz_clsfc": "시설ㆍ공간ㆍ보육"},
        {**s.KSTARTUP_POLICY, "pbanc_sn": "3", "biz_pbanc_nm": "2026년 청년 소상공인 점포 임차료 지원사업", "supt_biz_clsfc": "사업화"},
        {**s.KSTARTUP_POLICY, "pbanc_sn": "4", "biz_pbanc_nm": "2026년 서울창업센터 동작 입주기업 모집", "supt_biz_clsfc": "시설ㆍ공간ㆍ보육"},
    ]
    api.pages[list_url(source)] = s.kstartup_list(rows)
    run(source, api, web, policy_store, file_store, replace(policy_settings, detail_limit=0))
    state = {p.policy_id: (p.status, p.field) for p in policy_store.policies.values()}
    assert state == {
        "1": ("SKIPPED", "STARTUP_SUPPORT"),
        "2": ("SKIPPED", "STARTUP_SUPPORT"),
        "3": ("PENDING", "STARTUP_SUPPORT"),
        "4": ("PENDING", "SPACE_RECRUITMENT"),
    }


def test_kstartup_space_recruitment_reads_detail_page(api, web, policy_store, file_store, policy_settings):
    """K-Startup 사업공간 모집만 상세 화면 본문(입주공간 및 이용료)을 읽어요. 지원금 공고는 열지 않아요."""
    source = KStartupSource(KEY)
    page_url = "https://www.k-startup.go.kr/web/contents/bizpbanc-ongoing.do?schM=view&pbancSn=179600"
    space = {
        **s.KSTARTUP_POLICY,
        "pbanc_sn": "179600",
        "biz_pbanc_nm": "2026년 서울창업센터 동작 입주기업 모집",
        "supt_biz_clsfc": "시설ㆍ공간ㆍ보육",
        "detl_pg_url": page_url,
    }
    api.pages[list_url(source)] = s.kstartup_list([s.KSTARTUP_POLICY, space])
    web.pages[page_url] = kstartup_page(space["biz_pbanc_nm"])
    run(source, api, web, policy_store, file_store, policy_settings)
    assert web.requested == [page_url]  # 지원금 공고(179540)는 열지 않고, 첨부(/afile/)도 받지 않아요
    version = next(v for v in policy_store.versions if v.policy.policy_id == "179600")
    assert version.origin_status == "OK" and version.origin_text_url == page_url and version.files == []
    assert "모집공간: 3인실(18㎡) 1개" in version.full_text and "입주기간: 24개월" in version.full_text
    other = next(v for v in policy_store.versions if v.policy.policy_id == "179540")
    assert (other.document_status, other.origin_status) == ("NO_SOURCE", "NO_SOURCE")


def test_new_version_when_origin_text_is_gained(api, web, policy_store, file_store, policy_settings):
    """내용이 같아도 지난 버전에 원문 본문이 없었고 이번에 얻었으면 새 버전을 만들어요. 다시 열어 같은 본문이면 새 버전이 없어요."""
    source = KStartupSource(KEY)
    space = {**s.KSTARTUP_POLICY, "pbanc_sn": "179600", "biz_pbanc_nm": "2026년 서울창업센터 동작 입주기업 모집", "supt_biz_clsfc": "시설ㆍ공간ㆍ보육"}
    api.pages[list_url(source)] = s.kstartup_list([space])
    web.pages[space["detl_pg_url"]] = BlockedError("잠시 막힘")  # 첫 회차엔 본문을 못 읽음
    run(source, api, web, policy_store, file_store, policy_settings)
    assert [v.origin_status for v in policy_store.versions] == ["BLOCKED"]

    web.pages[space["detl_pg_url"]] = kstartup_page(space["biz_pbanc_nm"])
    assert run(source, api, web, policy_store, file_store, policy_settings, recheck=True).new_count == 1
    assert [v.origin_status for v in policy_store.versions] == ["BLOCKED", "OK"]
    assert run(source, api, web, policy_store, file_store, policy_settings, recheck=True).new_count == 0  # 본문이 있던 버전이면 그대로


def test_origin_page_is_opened_when_api_has_only_forms(api, web, policy_store, file_store, policy_settings):
    source = central(api, web)
    item = source.parse_list(s.BOKJIRO_CENTRAL_LIST).items[0]
    forms_only = s.BOKJIRO_CENTRAL_DETAIL.replace("<servSeDetailNm>청년전세임대 안내문<", "<servSeDetailNm>청년전세임대 신청서<")
    api.pages[detail_urls(source, item)[0]] = forms_only
    origin = source.parse_detail(item, [forms_only]).origin_urls[-1]  # 복지로 상세 화면
    page = s.ORIGIN_PAGE.replace("/cmm/fms/", "https://www.bokjiro.go.kr/cmm/fms/").replace("청년월세지원", "청년전세임대주택")
    web.pages[origin] = page
    web.files["https://www.bokjiro.go.kr/cmm/fms/FileDown.do?atchFileId=F1&fileSn=0"] = HWP
    run(source, api, web, policy_store, file_store, policy_settings)
    version = policy_store.versions[0]
    assert origin in version.origin_checked  # API 첨부가 서식뿐이라 원문에서 공고문을 찾았어요
    assert [(f.name, f.found_on) for f in version.files] == [("2026년 청년전세임대주택 모집공고문.hwp", "ORIGIN_PAGE")]
    assert not any("/files/form/" in u for u in web.requested)  # API 서식은 받지 않아요


def test_origin_page_is_opened_when_api_has_no_files(api, web, policy_store, file_store, policy_settings):
    result = run(youth(api, web), api, web, policy_store, file_store, policy_settings)
    assert result.new_count == 1
    version = policy_store.versions[0]
    assert [(f.name, f.role) for f in version.files] == [("2026년 청년월세지원 모집공고문.hwp", "POLICY_DOC")]
    assert "https://www.incheon.go.kr/cmm/fms/FileDown.do?atchFileId=F1&fileSn=2" not in web.requested  # 명단 파일
    assert version.origin_checked == ["https://www.incheon.go.kr/board/view.do?id=3301"]
    event = policy_store.events[0]
    validate_event(event)
    assert {f["foundOn"] for f in event["payload"]["files"]} == {"ORIGIN_PAGE"}
    assert event["payload"]["regionCodes"] == ["28177", "28185"]


def test_origin_page_text_is_added_when_relevant(api, web, policy_store, file_store, policy_settings):
    policy = {**s.YOUTH_POLICY, "plcyNm": "청년 농촌보금자리 조성사업"}
    source = youth(api, web, policy=policy, page=s.BOARD_PAGE)
    web.files["https://www.incheon.go.kr/cnportal/cmmn/file/fileDown.do?atchFileId=abc&fileSn=1"] = b"%PDF-1.4 scan"
    monkeypatch_text = pipeline.extract_text
    pipeline.extract_text = lambda data, ext: (None, "PDF에 글자가 거의 없음 (스캔본 가능성)")  # 카드뉴스 같은 그림 PDF
    try:
        run(source, api, web, policy_store, file_store, policy_settings)
    finally:
        pipeline.extract_text = monkeypatch_text
    version = policy_store.versions[0]
    assert "[원문 화면: https://www.incheon.go.kr/board/view.do?id=3301]" in version.full_text and "영농정착지원금" in version.full_text
    assert version.origin_text_url == "https://www.incheon.go.kr/board/view.do?id=3301"
    payload = policy_store.events[0]["payload"]
    assert payload["hasOriginText"] is True and payload["hasDocument"] is False  # 첨부는 받았지만 글자를 못 뽑았어요
    validate_event(policy_store.events[0])


def test_irrelevant_origin_page_text_is_not_added(api, web, policy_store, file_store, policy_settings):
    source = youth(api, web, page=s.HOME_PAGE)
    run(source, api, web, policy_store, file_store, policy_settings)
    version = policy_store.versions[0]
    assert "[원문 화면" not in version.full_text and version.origin_text_url is None
    assert policy_store.events[0]["payload"]["hasOriginText"] is False


def test_origin_page_text_does_not_change_the_version(api, web, policy_store, file_store, policy_settings):
    policy = {**s.YOUTH_POLICY, "plcyNm": "청년 농촌보금자리 조성사업"}
    source = youth(api, web, policy=policy, page=s.BOARD_PAGE.replace("</form>", "<p>오늘 방문자 1,024명</p></form>"))
    web.files["https://www.incheon.go.kr/cnportal/cmmn/file/fileDown.do?atchFileId=abc&fileSn=1"] = b"%PDF-1.4"
    run(source, api, web, policy_store, file_store, policy_settings)
    web.pages["https://www.incheon.go.kr/board/view.do?id=3301"] = s.BOARD_PAGE.replace("</form>", "<p>오늘 방문자 2,048명</p></form>")
    assert run(source, api, web, policy_store, file_store, policy_settings, recheck=True).new_count == 0


def test_unchanged_list_does_not_open_details_again(api, web, policy_store, file_store, policy_settings):
    source = central(api, web)
    run(source, api, web, policy_store, file_store, policy_settings)
    api.requested.clear()
    web.requested.clear()
    result = run(source, api, web, policy_store, file_store, policy_settings)
    assert result.new_count == 0 and api.requested == [list_url(source, 1)] and web.requested == []


def test_changed_marker_reopens_but_saves_only_real_changes(api, web, policy_store, file_store, policy_settings):
    source = BokjiroLocalSource(KEY)
    item = source.parse_list(s.BOKJIRO_LOCAL_LIST).items[0]
    api.pages[list_url(source, 1)] = s.BOKJIRO_LOCAL_LIST
    api.pages[detail_urls(source, item)[0]] = s.BOKJIRO_LOCAL_DETAIL
    web.pages["https://www.yeonsu.go.kr/notice/view.do?id=901"] = "<p>공고 본문만 있고 첨부는 없어요</p>"
    web.pages[f"{BOKJIRO_VIEW}?wlfareInfoId=WLF00005123&wlfareInfoReldBztpCd=02"] = "<p>복지로 화면</p>"
    assert run(source, api, web, policy_store, file_store, policy_settings).new_count == 1

    api.pages[list_url(source, 1)] = s.BOKJIRO_LOCAL_LIST.replace("20260903", "20260910")  # 수정일만 바뀜
    assert run(source, api, web, policy_store, file_store, policy_settings).new_count == 0
    assert policy_store.by_key("WLF00005123").status == "DONE"

    api.pages[list_url(source, 1)] = s.BOKJIRO_LOCAL_LIST.replace("20260903", "20260920")
    api.pages[detail_urls(source, item)[0]] = s.BOKJIRO_LOCAL_DETAIL.replace("월 20만원", "월 25만원")
    assert run(source, api, web, policy_store, file_store, policy_settings).new_count == 1
    assert policy_store.by_key("WLF00005123").latest_version == 2


# 출산장려금은 이주 혜택 단어가 없어서 1차 거름에서 빠져요 (실제로는 '주거' 태그가 붙어 있어요)
BIRTH = """  <servList>
    <servId>WLF00009001</servId>
    <servNm>출산장려금</servNm>
    <servDgst>출산 가정에 장려금을 지급해요</servDgst>
    <ctpvNm>인천광역시</ctpvNm><sggNm>연수구</sggNm>
    <lastModYmd>20260903</lastModYmd>
    <intrsThemaNmArray>임신·출산, 주거</intrsThemaNmArray>
  </servList>
</wantedList>"""


def local_with_birth(api, web):
    source = BokjiroLocalSource(KEY)
    item = source.parse_list(s.BOKJIRO_LOCAL_LIST).items[0]
    api.pages[list_url(source, 1)] = s.BOKJIRO_LOCAL_LIST.replace("<totalCount>1<", "<totalCount>2<").replace("</wantedList>", BIRTH)
    api.pages[detail_urls(source, item)[0]] = s.BOKJIRO_LOCAL_DETAIL
    web.pages["https://www.yeonsu.go.kr/notice/view.do?id=901"] = "<p>공고 본문만 있고 첨부는 없어요</p>"
    web.pages[f"{BOKJIRO_VIEW}?wlfareInfoId=WLF00005123&wlfareInfoReldBztpCd=02"] = "<p>복지로 화면</p>"
    return source


def test_local_policy_without_settle_words_is_skipped(api, web, policy_store, file_store, policy_settings):
    source = local_with_birth(api, web)
    assert run(source, api, web, policy_store, file_store, policy_settings).new_count == 1
    assert policy_store.by_key("WLF00005123").status == "DONE"
    skipped = policy_store.by_key("WLF00009001")
    assert skipped.status == "SKIPPED" and skipped.list_raw["servNm"] == "출산장려금"
    assert not any("WLF00009001" in url for url in api.requested)  # 상세를 열지 않아요


def test_waiting_policy_becomes_skipped_and_returns_when_words_widen(api, web, policy_store, file_store, policy_settings, monkeypatch):
    source = local_with_birth(api, web)
    monkeypatch.setattr(BokjiroLocalSource, "wanted", lambda self, item: True)
    run(source, api, web, policy_store, file_store, replace(policy_settings, detail_limit=0))  # 거름 전에 쌓인 PENDING
    assert policy_store.by_key("WLF00009001").status == "PENDING"

    monkeypatch.undo()
    run(source, api, web, policy_store, file_store, replace(policy_settings, detail_limit=0))
    assert policy_store.by_key("WLF00009001").status == "SKIPPED"

    monkeypatch.setattr(BokjiroLocalSource, "wanted", lambda self, item: True)  # 단어를 넓힌 경우
    run(source, api, web, policy_store, file_store, replace(policy_settings, detail_limit=0))
    assert policy_store.by_key("WLF00009001").status == "PENDING"


def test_central_policy_without_settle_words_is_skipped(api, web, policy_store, file_store, policy_settings):
    source = central(api, web)
    care = BIRTH.replace("WLF00009001", "WLF00000024").replace("출산장려금", "아이돌봄서비스")
    care = care.replace("출산 가정에 장려금을 지급해요", "육아 도우미가 방문하여 양육을 도와줍니다")
    api.pages[list_url(source, 1)] = s.BOKJIRO_CENTRAL_LIST.replace("</wantedList>", care)
    assert run(source, api, web, policy_store, file_store, policy_settings).new_count == 1
    assert policy_store.by_key("WLF00000024").status == "SKIPPED"
    assert not any("WLF00000024" in url for url in api.requested)


@pytest.mark.parametrize(
    "name, digest, expected",
    [
        ("2026년 충청남도 청년 주택임차보증금 이자 지원사업", "충청남도 청년들의 주거비용 부담 완화", True),
        ("관악구 청년 주거환경개선비 지원 사업", "", True),
        ("귀농인 정착지원금", "", True),
        ("전입 대학생 생활지원금", "", True),
        ("농촌빈집정비지원(일반)", "", True),
        ("의료급여수급자 암검진 바우처", "저소득층의 위, 대장, 유방암 검진시 발생되는 비급여 비용지원", False),
        ("첫째아 출산지원금", "출산지원금을 지급하여 양육부담을 경감", False),
        ("효도수당 지원", "경로효친의 건전한 가족제도 정착과 지역사회의 효 문화 확산", False),
        ("탈시설 장애인 자립정착금 지원", "", True),
        ("영주귀국 사할린한인 정착비 및 시설운영 지원", "", True),
        ("의성군 출산장려금 지원", "인구감소 대응을 위해 출산 가정에 장려금 지급", False),
    ],
)
def test_settle_words(name, digest, expected):
    item = PolicyItem("WLF1", name, "", {"servNm": name, "servDgst": digest})
    assert BokjiroLocalSource(KEY).wanted(item) is expected


def test_recheck_reopens_unchanged_policies(api, web, policy_store, file_store, policy_settings):
    source = central(api, web)
    run(source, api, web, policy_store, file_store, policy_settings)
    detail_url = detail_urls(source, source.parse_list(s.BOKJIRO_CENTRAL_LIST).items[0])[0]
    api.pages[detail_url] = s.BOKJIRO_CENTRAL_DETAIL.replace("1억 2천만원", "1억 3천만원")
    assert run(source, api, web, policy_store, file_store, policy_settings).new_count == 0  # 목록이 같아서 열지 않아요
    assert run(source, api, web, policy_store, file_store, policy_settings, recheck=True).new_count == 1


def test_robots_blocked_origin_is_skipped_once_per_run(api, web, policy_store, file_store, policy_settings):
    source = YouthSource(KEY)
    second = {**s.YOUTH_POLICY, "plcyNo": "2026SECOND", "refUrlAddr1": "https://www.incheon.go.kr/board/view.do?id=3302"}
    api.pages[list_url(source, 1)] = s.youth_list([s.YOUTH_POLICY, second])
    web.pages["https://www.incheon.go.kr/board/view.do?id=3301"] = BlockedError("robots.txt가 막은 주소라 요청하지 않아요")
    result = run(source, api, web, policy_store, file_store, policy_settings)
    assert result.status == "SUCCESS" and result.new_count == 2
    assert len([w for w in result.warnings if "www.incheon.go.kr" in w]) == 1
    assert web.requested == ["https://www.incheon.go.kr/board/view.do?id=3301"]  # 두 번째 정책은 같은 도메인이라 묻지 않아요
    assert {(v.document_status, v.origin_status) for v in policy_store.versions} == {("BLOCKED", "BLOCKED")}  # 묻지 않아도 BLOCKED


def test_gov24_does_not_open_origin(api, web, policy_store, file_store, policy_settings):
    """보조금24 원문(www.gov.kr)은 robots.txt 금지라 열지 않아요 (attachments = NEVER). 내용은 API 칸으로 채워요."""
    source = Gov24Source(KEY)
    api.pages[list_url(source, 1)] = s.GOV24_LIST
    for item in source.parse_list(s.GOV24_LIST).items:
        detail_url, conditions_url = detail_urls(source, item)
        api.pages[detail_url], api.pages[conditions_url] = s.gov24_detail(item.policy_id), s.gov24_conditions(item.policy_id)
    result = run(source, api, web, policy_store, file_store, policy_settings)
    assert result.status == "SUCCESS" and result.new_count == 2 and not result.warnings
    assert web.requested == []  # robots.txt도 묻지 않아요
    assert {(v.document_status, v.origin_status) for v in policy_store.versions} == {("NOT_NEEDED", "NOT_OPENED")}
    first = policy_store.versions[0]
    assert first.fields.detail_url == "https://www.gov.kr/portal/rcvfvrSvc/dtlEx/000000465790"  # 사람이 볼 링크는 그대로
    assert (first.fields.age_min, first.fields.age_max, first.fields.documents) == (19, 34, "신분증, 임대차계약서")
    assert first.fields.target == "만 19~34세 부모와 별도 거주하는 무주택 청년" and first.fields.apply_period == "2026. 12. 31.까지"
    assert "구비서류: 신분증, 임대차계약서" in first.body_text  # 버전 비교에는 전체 항목
    assert "구비서류" not in first.full_text and "선정기준: 청년가구 기준중위소득 60% 이하" in first.full_text  # AI 입력에는 설명 칸만


def test_paging_counts_items_without_id(api, web, policy_store, file_store, policy_settings):
    """ID 없는 항목을 버려도 페이지 넘김은 응답에 온 항목 수로 판단해요 (꽉 찬 페이지를 마지막 페이지로 착각하지 않게)."""
    source = KStartupSource(KEY)
    source.page_size = 2
    no_id = {**s.KSTARTUP_POLICY, "pbanc_sn": None}
    second = {**s.KSTARTUP_POLICY, "pbanc_sn": "179541"}
    api.pages[list_url(source, 1)] = s.kstartup_list([s.KSTARTUP_POLICY, no_id], total=3)
    api.pages[list_url(source, 2)] = s.kstartup_list([second], total=3)
    result = run(source, api, web, policy_store, file_store, replace(policy_settings, detail_limit=0))
    assert list_url(source, 2) in api.requested
    assert {p.policy_id for p in policy_store.policies.values()} == {"179540", "179541"}
    assert any("ID가 없는 항목 1건" in w for w in result.warnings)


def test_list_failure_marks_run_failed_but_processes_queue(api, web, policy_store, file_store, policy_settings):
    source = KStartupSource(KEY)
    api.pages[list_url(source, 1)] = s.kstartup_list([s.KSTARTUP_POLICY])
    run(source, api, web, policy_store, file_store, replace(policy_settings, detail_limit=0))  # 목록만 읽어 PENDING으로 쌓아 둬요
    api.pages[list_url(source, 1)] = "<html>점검 중</html>"
    result = run(source, api, web, policy_store, file_store, policy_settings)
    assert result.status == "FAILED" and any("목록 1페이지를 읽지 못해" in w for w in result.warnings)
    assert result.new_count == 1 and policy_store.by_key("179540").status == "DONE"  # 이미 쌓인 정책은 처리해요


def test_missing_key_fails_without_requests(api, web, policy_store, file_store, policy_settings):
    result = run(Gov24Source(None), api, web, policy_store, file_store, policy_settings)
    assert result.status == "FAILED" and "DATA_GO_KR_SERVICE_KEY" in result.warnings[0] and api.requested == []


def test_key_error_blocks_and_hides_key(api, web, policy_store, file_store, policy_settings):
    source = Gov24Source(KEY)
    url = list_url(source, 1)
    request = httpx.Request("GET", url)
    api.pages[url] = httpx.HTTPStatusError(f"HTTP 500: {url}", request=request, response=httpx.Response(500, request=request))
    result = run(source, api, web, policy_store, file_store, policy_settings)
    assert result.status == "FAILED" and result.warnings  # 목록을 못 읽으면 회차는 실패 (다음 회차에 다시)
    assert not any(KEY in w or "SeCrEt%2BKey" in w for w in result.warnings)

    api.pages[url] = s.GOV24_KEY_ERROR
    blocked = run(source, api, web, policy_store, file_store, policy_settings)
    assert blocked.status == "BLOCKED"


def test_http_401_blocks_without_failing_policies(api, web, policy_store, file_store, policy_settings):
    """보조금24는 키 오류를 HTTP 401로 줘요. 정책 FAILED로 쌓으면 3번 뒤엔 키를 고쳐도 다시 열지 않아서, 회차를 멈춰요."""
    source = Gov24Source(KEY)
    api.pages[list_url(source, 1)] = s.GOV24_LIST
    items = source.parse_list(s.GOV24_LIST).items
    for item in items:
        for url in detail_urls(source, item):
            request = httpx.Request("GET", url)
            api.pages[url] = httpx.HTTPStatusError(f"HTTP 401: {url}", request=request, response=httpx.Response(401, request=request))
    for _ in range(MAX_ATTEMPTS + 1):
        result = run(source, api, web, policy_store, file_store, policy_settings)
        assert result.status == "BLOCKED" and not any(KEY in w for w in result.warnings)
    assert {(p.status, p.attempts) for p in policy_store.policies.values()} == {("PENDING", 0)}

    for item in items:  # 키를 고치면 밀린 정책을 처리해요
        detail_url, conditions_url = detail_urls(source, item)
        api.pages[detail_url], api.pages[conditions_url] = s.gov24_detail(item.policy_id), s.gov24_conditions(item.policy_id)
    fixed = run(source, api, web, policy_store, file_store, policy_settings)
    assert fixed.status == "SUCCESS" and {p.status for p in policy_store.policies.values()} == {"DONE"}


def test_broken_detail_marks_only_that_policy_failed(api, web, policy_store, file_store, policy_settings):
    source = central(api, web, detail="<wantedDtl><resultCode>0</resultCode></wantedDtl>")
    result = run(source, api, web, policy_store, file_store, policy_settings)
    post = policy_store.by_key("WLF00001188")
    assert result.status == "SUCCESS" and post.status == "FAILED" and post.attempts == 1
    assert any("상세를 읽지 못했어요" in w for w in result.warnings)


def test_detail_limit_leaves_rest_pending(api, web, policy_store, file_store, policy_settings):
    source = Gov24Source(KEY)
    api.pages[list_url(source, 1)] = s.GOV24_LIST
    for item in source.parse_list(s.GOV24_LIST).items:
        detail_url, conditions_url = detail_urls(source, item)
        api.pages[detail_url], api.pages[conditions_url] = s.gov24_detail(item.policy_id), s.gov24_conditions(item.policy_id)
    run(source, api, web, policy_store, file_store, replace(policy_settings, detail_limit=1))
    assert sorted(p.status for p in policy_store.policies.values()) == ["DONE", "PENDING"]


def test_event_matches_contract_with_empty_values():
    from uuid import UUID

    event = build_policy_event(
        raw_policy_id=UUID("01929a3e-0000-7000-8000-000000000001"),
        version=1,
        source_code="gov24",
        provider="GOV24",
        field="BENEFIT",
        policy_id="000000465790",
        title="청년 월세 한시 특별지원",
        agency=None,
        region_scope="UNKNOWN",
        region_names=[],
        region_codes=[],
        categories=[],
        detail_url=None,
        apply_url=None,
        source_modified_at=None,
        full_text="가" * 200_010,
        text_key="text/gov24/000000465790/v1.txt",
        record={"서비스ID": "000000465790"},
        files=[],
    )
    validate_event(event)
    assert len(event["payload"]["text"]) == 200_000


# ── 보조금24: 이주 단어 거름 + 상세 한꺼번에 받기 ─────────────────────
def gov24_with_unrelated():
    data = json.loads(s.GOV24_LIST)
    data["data"].append(
        {
            "서비스ID": "105100000001",
            "서비스명": "근로·자녀장려금",
            "서비스목적요약": "소득이 적은 근로자에게 장려금 지급",
            "서비스분야": "주거·자립",
            "수정일시": "20260430093900",
        }
    )
    data["totalCount"] = data["currentCount"] = 3
    return json.dumps(data, ensure_ascii=False)


def bulk_url(source, endpoint):
    return build_url(f"{gov24.BASE}/{endpoint}", {"page": 1, "perPage": gov24.BULK_PAGE, "serviceKey": source.api_key})


def bulk_body(rows):
    return json.dumps({"page": 1, "perPage": gov24.BULK_PAGE, "totalCount": len(rows), "currentCount": len(rows), "data": rows}, ensure_ascii=False)


def test_gov24_skips_policies_without_settle_words(api, web, policy_store, file_store, policy_settings):
    source = Gov24Source(KEY)
    api.pages[list_url(source, 1)] = gov24_with_unrelated()
    for item in source.parse_list(s.GOV24_LIST).items:
        detail_url, conditions_url = detail_urls(source, item)
        api.pages[detail_url], api.pages[conditions_url] = s.gov24_detail(item.policy_id), s.gov24_conditions(item.policy_id)
    web.pages["https://www.gov.kr/portal/rcvfvrSvc/dtlEx/000000465790"] = BlockedError("robots.txt가 막은 주소라 요청하지 않아요")
    assert run(source, api, web, policy_store, file_store, policy_settings).new_count == 2  # 정책이 적어서 정책마다 받아요
    assert policy_store.by_key("105100000001").status == "SKIPPED"  # 서비스분야는 주거·자립이지만 이주 단어가 없어요
    assert not any("105100000001" in url for url in api.requested)


def test_gov24_prefetches_details_in_bulk(api, web, policy_store, file_store, policy_settings, monkeypatch):
    monkeypatch.setattr(gov24, "BULK_MIN", 1)
    source = Gov24Source(KEY)
    api.pages[list_url(source, 1)] = gov24_with_unrelated()
    ids = ["000000465790", "641000000123", "105100000001"]
    api.pages[bulk_url(source, "serviceDetail")] = bulk_body([json.loads(s.gov24_detail(i))["data"][0] for i in ids])
    api.pages[bulk_url(source, "supportConditions")] = bulk_body([json.loads(s.gov24_conditions(i))["data"][0] for i in ids])
    web.pages["https://www.gov.kr/portal/rcvfvrSvc/dtlEx/000000465790"] = BlockedError("robots.txt가 막은 주소라 요청하지 않아요")
    assert run(source, api, web, policy_store, file_store, policy_settings).new_count == 2
    assert api.requested == [list_url(source, 1), bulk_url(source, "serviceDetail"), bulk_url(source, "supportConditions")]
    record = policy_store.versions[0].api_raw
    assert record["구비서류"] == "신분증, 임대차계약서" and record["지원조건"]["대상연령"] == "19~34"
    assert set(source.details) == {"000000465790", "641000000123"}  # 거름을 통과한 정책만 남겨요


def test_gov24_falls_back_to_each_policy_when_bulk_fails(api, web, policy_store, file_store, policy_settings, monkeypatch):
    monkeypatch.setattr(gov24, "BULK_MIN", 1)
    source = Gov24Source(KEY)
    api.pages[list_url(source, 1)] = s.GOV24_LIST
    api.pages[bulk_url(source, "serviceDetail")] = "<html>점검 중</html>"
    for item in source.parse_list(s.GOV24_LIST).items:
        detail_url, conditions_url = detail_urls(source, item)
        api.pages[detail_url], api.pages[conditions_url] = s.gov24_detail(item.policy_id), s.gov24_conditions(item.policy_id)
    web.pages["https://www.gov.kr/portal/rcvfvrSvc/dtlEx/000000465790"] = BlockedError("robots.txt가 막은 주소라 요청하지 않아요")
    result = run(source, api, web, policy_store, file_store, policy_settings)
    assert result.new_count == 2 and any("한꺼번에 받지 못해" in w for w in result.warnings)


# ── 온통청년: 전체를 받고 주거·창업만 ─────────────────────────────────
def test_youth_takes_housing_and_startup_from_full_list(api, web, policy_store, file_store, policy_settings):
    source = YouthSource(KEY)
    startup = {
        **s.YOUTH_POLICY,
        "plcyNo": "2026STARTUP",
        "plcyNm": "청년 창업 공간 입주 지원",
        "lclsfNm": "일자리",
        "mclsfNm": "취업,창업",
        "refUrlAddr1": None,
    }
    move_in = {
        **s.YOUTH_POLICY,
        "plcyNo": "2026MOVEIN",
        "plcyNm": "전입세대 전입장려금 지원",
        "lclsfNm": "금융･복지･문화",
        "mclsfNm": "문화활동 및 생활지원",
        "refUrlAddr1": None,
    }
    other = {
        **s.YOUTH_POLICY,
        "plcyNo": "2026OTHER",
        "plcyNm": "청년 자격증 응시료 지원",
        "plcyExplnCn": "자격증 시험 응시료 지원",
        "lclsfNm": "교육",
        "mclsfNm": "교육비지원",
    }
    api.pages[list_url(source, 1)] = s.youth_list([s.YOUTH_POLICY, startup, move_in, other])
    assert "lclsfNm" not in list_url(source, 1) and "pageSize=500" in list_url(source, 1)
    web.pages["https://www.incheon.go.kr/board/view.do?id=3301"] = s.ORIGIN_PAGE
    web.files["https://www.incheon.go.kr/cmm/fms/FileDown.do?atchFileId=F1&fileSn=0"] = HWP
    web.files["https://www.incheon.go.kr/cmm/fms/FileDown.do?atchFileId=F1&fileSn=1"] = HWP + b"form"
    assert run(source, api, web, policy_store, file_store, policy_settings).new_count == 3
    assert policy_store.by_key("2026OTHER").status == "SKIPPED"
    fields = {e["payload"]["policyId"]: e["payload"]["field"] for e in policy_store.events}
    assert fields == {"20260815005400211234": "BENEFIT", "2026STARTUP": "STARTUP_SUPPORT", "2026MOVEIN": "BENEFIT"}


# ── 정책 전용 테이블: 통일한 칸과 첨부·원문 상태 ───────────────────────
def test_bokjiro_central_skips_documents(api, web, policy_store, file_store, policy_settings):
    run(central(api, web, attachments=BokjiroCentralSource.attachments), api, web, policy_store, file_store, policy_settings)
    version = policy_store.versions[0]
    assert BokjiroCentralSource.attachments == "NEVER"
    assert (version.document_status, version.origin_status, version.files) == ("NOT_NEEDED", "NOT_OPENED", [])
    assert web.requested == []  # 첨부도 원문 화면도 열지 않아요
    validate_event(policy_store.events[0])


def test_bokjiro_local_reads_documents_only_when_api_is_thin():
    source = BokjiroLocalSource(KEY)
    long_text = "지원대상: 관내 거주 무주택 청년 " * 100
    assert source.attachments == "WHEN_THIN"
    assert source.needs_documents({"servNm": "청년 월세", "sprtTrgtCn": "관내 청년"})  # 짧아요
    assert not source.needs_documents({"servNm": "청년 월세", "sprtTrgtCn": long_text})
    assert source.needs_documents({"servNm": "청년 월세", "sprtTrgtCn": long_text, "alwServCn": "세부 내용은 공고문 참조"})


def test_ai_text_keeps_description_fields_only():
    source = BokjiroLocalSource(KEY)
    record = {"servNm": "청년 월세", "slctCritCn": "·자격\r - 만19세\r - 무주택", "servDtlLink": "https://x", "basfrmList": [{"a": 1}]}
    text = source.ai_text(record)
    assert "https://x" not in text and "basfrmList" not in text and "\r" not in text
    assert "만19세" in text and source.body_text(record).count("https://x") == 1


def test_unified_fields_and_statuses_with_api_files(api, web, policy_store, file_store, policy_settings):
    run(central(api, web), api, web, policy_store, file_store, policy_settings)
    version = policy_store.versions[0]
    assert (version.document_status, version.origin_status) == ("OK", "NOT_OPENED")  # API 첨부가 있어서 원문은 열지 않아요
    assert version.fields.title == "청년 전세임대주택" and version.fields.target == "무주택 청년(만 19~39세)"
    assert version.fields.field == "BENEFIT" and version.fields.region_scope == "NATIONWIDE"
    assert all(f.found_on == "API" for f in version.files)
    payload = policy_store.events[0]["payload"]
    assert (payload["documentStatus"], payload["originStatus"]) == ("OK", "NOT_OPENED")


def test_youth_closed_policy_is_skipped_until_reopened(api, web, policy_store, file_store, policy_settings):
    source = YouthSource(KEY)
    closed = {**s.YOUTH_POLICY, "aplyPrdSeCd": "0057001", "aplyYmd": "20260123 ~ 20260202", "refUrlAddr1": None}
    api.pages[list_url(source, 1)] = s.youth_list([closed])
    run(source, api, web, policy_store, file_store, policy_settings)
    assert [p.status for p in policy_store.policies.values()] == ["SKIPPED"] and not policy_store.versions

    reopened = {**closed, "aplyYmd": "20261012 ~ 20261130", "lastMdfcnDt": "2026-10-12 09:00:00"}
    api.pages[list_url(source, 1)] = s.youth_list([reopened])
    run(source, api, web, policy_store, file_store, policy_settings)
    assert [p.status for p in policy_store.policies.values()] == ["DONE"] and len(policy_store.versions) == 1


def test_no_origin_address_and_irrelevant_page(api, web, policy_store, file_store, policy_settings):
    source = YouthSource(KEY)
    no_ref = {**s.YOUTH_POLICY, "plcyNo": "2026NOREF", "refUrlAddr1": None, "refUrlAddr2": None}
    home = {**s.YOUTH_POLICY, "plcyNo": "2026HOME", "refUrlAddr1": "https://www.example.go.kr/main.do", "refUrlAddr2": None}
    api.pages[list_url(source, 1)] = s.youth_list([no_ref, home])
    web.pages["https://www.example.go.kr/main.do"] = "<div>" + "시청 소식과 행사 안내 " * 40 + "</div>"
    run(source, api, web, policy_store, file_store, policy_settings)
    states = {v.policy.policy_id: (v.document_status, v.origin_status) for v in policy_store.versions}
    assert states == {"2026NOREF": ("NO_SOURCE", "NO_SOURCE"), "2026HOME": ("NONE", "NONE")}
    assert policy_store.versions[0].fields.age_min == 19


def test_a_flaky_attachment_does_not_flip_the_policy_version(api, web, policy_store, file_store, policy_settings):
    """2026-11-10 재검토: 연결 오류 한 번에 버전이 v1(첨부 있음) → v2(첨부 없음) → v3(첨부 있음)으로 오락가락해 추출·알림이 다시 돌았어요.
    게시판 수집과 같이 실패로 세어 다시 받고, 마지막 시도엔 이전 버전의 같은 첨부를 이어 써요(처음이면 그 파일 없이)."""
    import httpx

    from mujuthaek_collector.core.storage import MAX_ATTEMPTS

    source = central(api, web)
    url = "https://www.bokjiro.go.kr/files/form/청년전세임대_안내문.pdf"
    web.files[url] = httpx.ConnectError("연결 끊김")
    for attempt in range(1, MAX_ATTEMPTS):
        assert run(source, api, web, policy_store, file_store, policy_settings).new_count == 0
        assert (policy_store.by_key("WLF00001188").status, policy_store.by_key("WLF00001188").attempts) == ("FAILED", attempt)
    assert run(source, api, web, policy_store, file_store, policy_settings).new_count == 1  # 마지막 시도: 처음이라 그 파일 없이
    assert policy_store.versions[-1].files == []

    web.files[url] = PDF
    policy_store.by_key("WLF00001188").status = "PENDING"  # 목록이 바뀌어 다시 열 때처럼
    assert run(source, api, web, policy_store, file_store, policy_settings).new_count == 1
    assert [f.role for f in policy_store.versions[-1].files] == ["POLICY_DOC"]

    web.files[url] = httpx.ConnectError("연결 끊김")
    policy_store.by_key("WLF00001188").status = "PENDING"
    for _ in range(MAX_ATTEMPTS - 1):
        assert run(source, api, web, policy_store, file_store, policy_settings).new_count == 0
    assert run(source, api, web, policy_store, file_store, policy_settings).new_count == 0  # 이전 첨부를 이어 써 내용이 같음
    assert len(policy_store.versions) == 2 and policy_store.by_key("WLF00001188").status == "DONE"
    assert policy_store.by_key("WLF00001188").attempts == 0
