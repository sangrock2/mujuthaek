"""LH 출처를 팀 공통 파이프라인으로 끝까지 돌려봐요 (가짜 API·메모리 저장소). 이벤트는 계약 파일로 검사해요."""

import copy
from datetime import date

import pytest

from mujuthaek_collector import pipeline
from mujuthaek_collector.sources.lh import config
from mujuthaek_collector.sources.lh.source import LhSource
from mujuthaek_platform.contracts import validate_event
from tests.sources.lh.helpers import PAN, PDF_URL, taebaek_myhome_row, with_rows

TODAY = date(2026, 10, 14)
XLSX_URL = "https://apply.lh.or.kr/lhapply/lhFile.do?fileid=99"
MYHOME_RENT = f"{config.MYHOME_URL}/{config.MYHOME_LISTS['rent']}"
MYHOME_SALE = f"{config.MYHOME_URL}/{config.MYHOME_LISTS['sale']}"
LISTS_ONLY = [config.LIST_URL, MYHOME_RENT, MYHOME_SALE]


class Clock:
    """마이홈 목록 캐시용 시계. 회차 사이에 시간을 넉넉히 흘려요."""

    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


@pytest.fixture
def source():
    return LhSource(today=lambda: TODAY, clock=Clock())


@pytest.fixture
def run(store, file_store, settings, monkeypatch):
    monkeypatch.setattr(pipeline, "extract_text", lambda data, ext: ("공고문 글자 " * 40, "PDF 텍스트·표") if ext == "pdf" else (None, "읽지 않음"))

    def go(source, client, **kwargs):
        source._clock.now += 3600  # 다음 회차 (마이홈 목록 캐시가 지나요)
        return pipeline.run_source(source, client, store, file_store, settings, today=TODAY, **kwargs)

    return go


def attach(detail_body, *files):
    body = copy.deepcopy(detail_body)
    for block in body:
        if "dsAhflInfo" in block:
            block["dsAhflInfo"] += [{"SL_PAN_AHFL_DS_CD_NM": kind, "CMN_AHFL_NM": name, "AHFL_URL": url} for kind, name, url in files]
    return body


def only_land(list_body):
    return with_rows(list_body, [{"PAN_ID": "L1", "PAN_NM": "○○지구 공동주택용지 공급", "UPP_AIS_TP_NM": "토지"}])


# ── 기본 흐름 ──────────────────────────────────────
def test_first_run_saves_raw_files_and_a_valid_event(source, lh, run, store, file_store, detail_body):
    result = run(source, lh)
    assert (result.status, result.new_count) == ("SUCCESS", 1) and result.warnings == []

    post = store.by_key(PAN)
    assert (post.board_key, post.kind, post.status, post.list_status) == ("open", "NOTICE", "DONE", "공고중")
    assert len(store.posts) == 1  # 마이홈에도 있는 공고는 한 번만 (LH 공고 ID가 글 키)

    [version] = store.versions
    raw = version.meta["_raw"]
    assert raw["detail"]["body"][1]["dsAhflInfo"] == detail_body[1]["dsAhflInfo"]  # 원본 응답 그대로
    assert "serviceKey" not in raw["detail"]["params"] and raw["myhome"][0]["item"]["pnu"] == "5119010700100600000"
    assert "_raw" not in version.full_text and "RS_DTTM" not in version.full_text  # 원본은 AI 글자에 넣지 않아요
    assert "공고유형: 국민임대" in version.full_text and "[공급일정]" in version.full_text
    assert "금회공급 세대수: 60" in version.full_text  # 공급정보 표는 글자로 넘기고 해석은 extraction이 해요

    [f] = version.files
    assert (f.role, f.download_url) == ("NOTICE_DOC", PDF_URL)
    assert any(key.startswith(f"raw/lh/{PAN}/v1/01-") for key in file_store.objects)  # 첨부 목록 순서 1번(PDF)

    [event] = store.events
    validate_event(event)  # contracts/events/raw.notice.collected.v1.json
    payload = event["payload"]
    assert (payload["sourceCode"], payload["provider"], payload["kind"], payload["regionCode"]) == ("lh", "LH", "NOTICE", "51190")
    [event_file] = payload["files"]
    assert (event_file["downloadUrl"], event_file["role"], event_file["fileType"]) == (PDF_URL, "NOTICE_DOC", "pdf")
    assert event_file["s3Key"] in file_store.objects  # extraction은 이 위치에서 원본을 읽어요
    assert payload["units"] == []  # 호별 임대조건은 extraction이 원본에서 읽어요 (#19)


def test_second_run_reads_only_the_lists(source, lh, run, store):
    run(source, lh)
    lh.calls.clear()
    result = run(source, lh)
    assert result.new_count == 0 and lh.calls == LISTS_ONLY and len(store.versions) == 1


def test_recheck_ignores_response_time_but_catches_a_replaced_notice(source, lh, run, store, detail_body):
    run(source, lh)
    assert run(source, lh, recheck=True).new_count == 0  # 응답 시각만 바뀐 상세는 같은 버전
    lh.detail_body = attach(detail_body)
    for block in lh.detail_body:
        for f in block.get("dsAhflInfo", []):
            if f["AHFL_URL"] == PDF_URL:
                f["CMN_AHFL_NM"] = "260917태백시국민임대주택예비입주자상시모집공고문(수정).pdf"
    lh.files[PDF_URL] = b"%PDF-1.7 corrected notice"
    assert run(source, lh, recheck=True).new_count == 1  # LH가 같은 공고 안에서 공고문을 바꾼 경우
    assert store.by_key(PAN).latest_version == 2


def test_list_lines_leave_out_columns_that_change_every_run(source, lh, run, store, list_body):
    # 2026-11-10 재검토: 줄 번호·전체 건수(LH)와 받은 시각(마이홈)이 목록 줄에 있어, 목록에 있는 LH 글이 매시 모두 UPDATE됐음
    run(source, lh)
    first = store.by_key(PAN).list_item
    assert not {"RNUM", "ALL_CNT"} & set(first["meta"]["_lhRow"]) and first["meta"]["_lhRow"]["PAN_ID"] == PAN
    lh.open_list = copy.deepcopy(list_body)
    lh.open_list[1]["dsList"][0].update(RNUM="7", ALL_CNT="9")  # 다음 회차엔 줄 번호·전체 건수만 달라짐
    run(source, lh)
    assert store.by_key(PAN).list_item == first

    # 마이홈에만 보이는 공고의 줄에도 받은 시각을 두지 않음
    entries = source._myhome_item(source.boards[1], PAN, [{"list": "rent", "key": "k", "fetchedAt": "2026-10-15T00:00:00+00:00", "item": {}}])
    assert entries.meta["_myhome"] == [{"list": "rent", "key": "k", "item": {}}]


def test_correction_is_linked_to_its_original_although_the_api_lists_newest_first(source, lh, run, store, list_body):
    # 2026-10-16 실측: LH 정정공고 17건이 원래 공고보다 먼저 등록돼 하나도 연결되지 않았어요
    correction = {"PAN_ID": "2015122300020999", "PAN_NM": "[정정공고]태백소도 국민임대주택 예비입주자 상시모집(26.9.17 공고)", "PAN_NT_ST_DT": "2026.09.20"}
    lh.open_list = with_rows(list_body, [correction, {"PAN_ID": PAN}])  # LH API처럼 최신 공고가 먼저
    lh.myhome["rent"] = []
    run(source, lh)
    original, fixed = store.by_key(PAN), store.by_key(correction["PAN_ID"])
    assert (fixed.kind, fixed.parent_post_id) == ("CORRECTION", original.id)
    event = next(e["payload"] for e in store.events if e["payload"]["rawPostId"] == str(fixed.id))
    assert event["supersedesPostId"] == str(original.id)


# ── 마이홈 ─────────────────────────────────────────
def test_notice_only_on_myhome_is_found_in_the_lh_list(source, lh, run, store, list_body):
    lh.open_list = only_land(list_body)  # LH는 '접수마감'으로 바꿔 마감 전 목록에서 빠진 상시모집
    lh.lookup = lambda params: list_body if params.get("PAN_ST_DT") == "20260917" else None
    result = run(source, lh)
    post = store.by_key(PAN)
    assert (result.new_count, post.board_key, post.status) == (1, "myhome", "DONE")
    lookup = store.versions[0].meta["_raw"]["lookup"]
    assert lookup["params"]["PAN_ST_DT"] == lookup["params"]["PAN_ED_DT"] == "20260917"
    validate_event(store.events[0])


def test_myhome_only_notice_not_found_is_retried_next_run(source, lh, run, store, list_body):
    lh.open_list = only_land(list_body)
    result = run(source, lh)
    assert store.by_key(PAN).status == "FAILED" and any("LH 목록에서 찾지 못했어요" in w for w in result.warnings)
    lh.lookup = lambda params: list_body if params.get("PAN_ST_DT") == "20260917" else None
    run(source, lh)
    assert store.by_key(PAN).status == "DONE"


def test_old_myhome_notice_is_not_opened(source, lh, run, store, list_body):
    lh.open_list = only_land(list_body)
    lh.myhome["rent"] = [taebaek_myhome_row(rcritPblancDe="20250915")]  # 마이홈엔 아직 있지만 1년 넘은 공고 (예: 울산 정례모집)
    run(source, lh)
    assert store.by_key(PAN).status == "SKIPPED" and "365일" in store.by_key(PAN).last_error


def test_myhome_failure_is_a_warning_and_lh_is_still_collected(source, lh, run, store):
    lh.myhome_error = "<OpenAPI_ServiceResponse>SERVICE_KEY_IS_NOT_REGISTERED_ERROR</OpenAPI_ServiceResponse>"
    result = run(source, lh)
    assert result.status == "SUCCESS" and store.by_key(PAN).status == "DONE"
    assert any("마이홈 목록을 읽지 못했어요" in w for w in result.warnings)
    assert store.events[0]["payload"]["regionCode"] is None  # 마이홈 필지번호가 없으면 비워요


# ── 분류·첨부 ───────────────────────────────────────
def test_land_and_cancelled_notices_are_not_opened(source, lh, run, store, list_body):
    lh.open_list = with_rows(
        list_body,
        [
            {"PAN_ID": "L1", "PAN_NM": "○○지구 공동주택용지 공급", "UPP_AIS_TP_NM": "토지"},
            {"PAN_ID": "C1", "PAN_NM": "[취소공고]태백철암1 국민임대주택 예비입주자 모집 공고"},
        ],
    )
    lh.myhome["rent"] = []
    run(source, lh)
    assert {store.by_key("L1").status, store.by_key("C1").status} == {"SKIPPED"}
    assert config.DETAIL_URL not in lh.calls


def test_housing_list_spreadsheet_is_saved_as_unit_list_original(source, lh, run, store, file_store, detail_body):
    lh.detail_body = attach(detail_body, ("기타 첨부파일", "붙임3.매입임대주택목록.xlsx", XLSX_URL))
    lh.files[XLSX_URL] = b"PK\x03\x04 fake housing list"
    run(source, lh)
    [version] = store.versions
    assert [f.role for f in version.files] == ["NOTICE_DOC", "UNIT_LIST"]
    [event] = store.events
    validate_event(event)
    housing_list = next(f for f in event["payload"]["files"] if f["role"] == "UNIT_LIST")
    assert (housing_list["name"], housing_list["fileType"]) == ("붙임3.매입임대주택목록.xlsx", "xlsx")
    assert file_store.objects[housing_list["s3Key"]] == b"PK\x03\x04 fake housing list"  # 원본 그대로, 표 해석은 extraction이 해요
    assert event["payload"]["units"] == []


def test_appendix_typed_as_notice_is_recorded_not_downloaded(source, lh, run, store, detail_body):
    lh.detail_body = attach(detail_body, ("공고문(PDF)", "아산배방오피스텔동호수배치표.xlsx", XLSX_URL))
    run(source, lh)
    assert XLSX_URL not in lh.calls
    assert [a["name"] for a in store.versions[0].meta["_raw"]["extraAttachments"]] == ["아산배방오피스텔동호수배치표.xlsx"]


def test_reserve_tenant_notice_is_not_mistaken_for_a_name_list(source, lh, run, store, detail_body):
    # 공통 첨부 규칙이 '예비자'만 보고 명단으로 거르던 경우 (실제 LH 공고문 4건)
    body = copy.deepcopy(detail_body)
    for block in body:
        for f in block.get("dsAhflInfo", []):
            if f["AHFL_URL"] == PDF_URL:
                f["CMN_AHFL_NM"] = "20261007창녕영산1BL행복주택예비자모집공고문_게시용.pdf"
    lh.detail_body = body
    run(source, lh)
    assert [f.name for f in store.versions[0].files] == ["20261007창녕영산1BL행복주택예비자모집공고문_게시용.pdf"]


def test_missing_api_key_blocks_only_this_source(source, lh, run, store):
    lh.service_key = None
    result = run(source, lh)
    assert result.status == "BLOCKED" and config.API_KEY_ENV in result.warnings[0] and not store.posts


@pytest.mark.parametrize("env", ["ab%2Bcd%2Fef%3D%3D", "ab+cd/ef=="])
def test_api_key_copied_encoded_from_the_portal_is_decoded_once(source, settings, monkeypatch, env):
    monkeypatch.setenv(config.API_KEY_ENV, env)
    assert source.make_client(settings).service_key == "ab+cd/ef=="
