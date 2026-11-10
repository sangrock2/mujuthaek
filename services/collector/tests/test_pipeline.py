"""파이프라인 전체 흐름: 가짜 출처·가짜 클라이언트·메모리 저장소로 전체 흐름을 확인해요."""

from datetime import date

import httpx

from mujuthaek_collector import pipeline
from mujuthaek_collector.core.files import FileRef
from mujuthaek_collector.core.storage import MAX_ATTEMPTS
from mujuthaek_collector.errors import BlockedError, ParseError
from mujuthaek_collector.sources.base import Board, Detail, ListItem, Request, Source

TODAY = date(2026, 10, 14)


class FakeSource(Source):
    code, name, provider = "dcco", "가짜 기관", "TEST"
    boards = [Board("43", "임대")]

    def __init__(self, rows):
        self.rows = rows  # [(post_key, title, posted_on)]

    def list_request(self, board, page):
        return Request(f"https://a.kr/list?page={page}")

    def parse_list(self, board, body, page_url):
        if body == "BROKEN":
            raise ParseError("목록 표 없음")
        rows = self.rows if page_url.endswith("page=1") else []
        return [ListItem(board.key, key, title, day, f"https://a.kr/view?id={key}") for key, title, day in rows]

    def parse_detail(self, item, body):
        if body == "BROKEN":
            raise ParseError("본문 없음")
        return Detail(item.title, body, [FileRef("모집공고문.pdf", f"https://a.kr/f/{item.post_key}.pdf", 1)])


def pages(client, rows, body="본문"):
    for n in (1, 2, 3):
        client.pages[f"https://a.kr/list?page={n}"] = "list"
    for key, *_ in rows:
        client.pages[f"https://a.kr/view?id={key}"] = body
        client.files[f"https://a.kr/f/{key}.pdf"] = b"%PDF-1.4 fake"


def run(source, client, store, file_store, settings, monkeypatch, **kwargs):
    monkeypatch.setattr(pipeline, "extract_text", lambda data, ext: ("공고문 글자 " * 30, "PDF 텍스트·표"))
    return pipeline.run_source(source, client, store, file_store, settings, today=TODAY, **kwargs)


ROWS = [
    ("1", "2026년 행복주택 입주자 모집공고", date(2026, 10, 1)),
    ("2", "2026년 행복주택 입주자 모집공고(2026. 10. 1.) 서류심사 대상자 발표", date(2026, 10, 10)),
    ("3", "2026년 기존주택 매입 공고", date(2026, 10, 2)),
    ("4", "2026년 영구임대 입주자 모집공고(2026. 5. 1.) 당첨자 발표", date(2026, 10, 3)),
]


def test_new_posts_are_saved_with_event(client, store, file_store, settings, monkeypatch):
    pages(client, ROWS)
    result = run(FakeSource(ROWS), client, store, file_store, settings, monkeypatch)
    assert result.status == "SUCCESS" and result.new_count == 2
    assert store.by_key("1").status == "DONE"
    assert store.by_key("2").parent_post_id == store.by_key("1").id  # 후속 안내 → 원래 모집공고
    assert store.by_key("3").status == "SKIPPED"  # 매입 공고
    assert store.by_key("4").status == "SKIPPED"  # 원래 공고가 없는 후속 안내
    event = store.events[0]
    assert event["eventType"] == "raw.notice.collected" and event["payload"]["files"][0]["sha256"]
    assert any(key.startswith("raw/dcco/1/v1/") for key in file_store.objects)


def test_correction_listed_before_its_original_is_linked(client, store, file_store, settings, monkeypatch):
    """목록이 최신 글 먼저라 같은 회차에 정정공고가 원래 공고보다 먼저 등록돼도 이벤트에 원래 공고가 연결돼요."""
    rows = [
        ("11", "검암역 푸르지오 프라베뉴(검암B-1BL) 입주자모집공고[정정공고]", date(2026, 10, 5)),
        ("10", "검암역 푸르지오 프라베뉴(검암B-1BL) 입주자모집공고", date(2026, 10, 1)),
    ]
    pages(client, rows)
    run(FakeSource(rows), client, store, file_store, settings, monkeypatch)
    original, correction = store.by_key("10"), store.by_key("11")
    assert correction.kind == "CORRECTION" and correction.parent_post_id == original.id
    event = next(v.event for v in store.versions if v.post.id == correction.id)
    assert event["payload"]["supersedesPostId"] == str(original.id)


def test_correction_links_to_the_round_before_it_not_a_later_one(client, store, file_store, settings, monkeypatch):
    """매달 같은 이름으로 올라오는 공고: 정정공고는 자기보다 먼저 올라온 회차에 연결돼요 (LH 김제하동 국민임대 같은 경우)."""
    rows = [
        ("22", "김제하동 국민임대주택 모집공고", date(2026, 10, 7)),
        ("21", "김제하동 국민임대주택 모집공고", date(2026, 9, 7)),
        ("23", "[정정공고]김제하동 국민임대주택 모집공고", date(2026, 9, 8)),
    ]
    pages(client, rows)
    run(FakeSource(rows), client, store, file_store, settings, monkeypatch)
    assert store.by_key("23").parent_post_id == store.by_key("21").id


def test_correction_links_only_to_the_notice_with_the_same_block(client, store, file_store, settings, monkeypatch):
    """이름 비교는 괄호를 지워서, 괄호 안 블록이 다른 같은 이름 공고에 붙지 않게 구분도 맞춰 봐요 (2026-11-10 코드 검토)."""
    rows = [
        ("32", "행복주택 입주자 모집공고(A-2블록) [정정공고]", date(2026, 10, 5)),
        ("31", "행복주택 입주자 모집공고(A-3블록)", date(2026, 10, 3)),
        ("30", "행복주택 입주자 모집공고(A-2블록)", date(2026, 10, 1)),
    ]
    pages(client, rows)
    run(FakeSource(rows), client, store, file_store, settings, monkeypatch)
    assert store.by_key("32").parent_post_id == store.by_key("30").id


def test_correction_with_the_original_date_links_to_that_round(client, store, file_store, settings, monkeypatch):
    """2026-11-10 재검토: 공고일 뒤에 바뀐 내용을 적은 정정 제목은 후속 안내로 분류됐고, 공고일·꾸밈말 괄호까지 견줘 원래 공고와 끊겼어요.
    제목의 공고일이 있으면 그날 올라온 회차에 붙어요."""
    rows = [
        ("42", "[정정공고] 김제하동 국민임대주택 모집공고(2026.09.07) 당첨자 발표일 변경", date(2026, 10, 9)),
        ("41", "김제하동 국민임대주택 모집공고(수요자맞춤형)", date(2026, 10, 7)),
        ("40", "김제하동 국민임대주택 모집공고(수요자맞춤형)", date(2026, 9, 7)),
    ]
    pages(client, rows)
    run(FakeSource(rows), client, store, file_store, settings, monkeypatch)
    assert store.by_key("42").kind == "CORRECTION" and store.by_key("42").parent_post_id == store.by_key("40").id


class TwoBoardSource(FakeSource):
    """LH처럼 두 게시판이 같은 글 번호를 쓰는 출처. 게시판마다 상세 주소가 달라요."""

    boards = [Board("open", "분양임대"), Board("myhome", "마이홈")]

    def parse_list(self, board, body, page_url):
        items = super().parse_list(board, body, page_url)
        for item in items:
            item.detail_url = f"{item.detail_url}&board={board.key}"
        return items


def test_a_post_listed_on_two_boards_keeps_the_list_line_of_its_own_board(client, store, file_store, settings, monkeypatch):
    """2026-11-10 재검토: 다른 게시판의 줄로 목록 값을 덮어, 정정 확인 때 상세를 다른 게시판 주소로 열었어요."""
    rows = ROWS[:1]
    pages(client, rows)
    for board in ("open", "myhome"):
        client.pages[f"https://a.kr/view?id=1&board={board}"] = "본문"
    run(TwoBoardSource(rows), client, store, file_store, settings, monkeypatch)
    run(TwoBoardSource(rows), client, store, file_store, settings, monkeypatch, recheck=True)
    post = store.by_key("1")
    assert post.board_key == "open" and post.list_item["detail_url"].endswith("board=open")


def test_event_files_point_to_uploaded_s3_objects(client, store, file_store, settings, monkeypatch):
    """이벤트의 s3Key는 실제로 올린 S3 경로와 같고, 받는 쪽은 role로 공고문을 찾아요."""
    rows = ROWS[:1]
    pages(client, rows)
    run(FakeSource(rows), client, store, file_store, settings, monkeypatch)
    (file,) = store.events[0]["payload"]["files"]
    assert file["s3Key"] == "raw/dcco/1/v1/01-모집공고문.pdf" and file["s3Key"] in file_store.objects
    assert (file["role"], file["fileType"], file["name"]) == ("NOTICE_DOC", "pdf", "모집공고문.pdf")


def test_same_list_next_time_stops_after_first_page(client, store, file_store, settings, monkeypatch):
    pages(client, ROWS)
    run(FakeSource(ROWS), client, store, file_store, settings, monkeypatch)
    client.requested.clear()
    result = run(FakeSource(ROWS), client, store, file_store, settings, monkeypatch)
    assert result.new_count == 0 and client.requested == ["https://a.kr/list?page=1"]


def test_recheck_creates_new_version_only_when_changed(client, store, file_store, settings, monkeypatch):
    rows = ROWS[:1]
    pages(client, rows)
    run(FakeSource(rows), client, store, file_store, settings, monkeypatch)
    assert run(FakeSource(rows), client, store, file_store, settings, monkeypatch, recheck=True).new_count == 0
    client.pages["https://a.kr/view?id=1"] = "정정된 본문"
    assert run(FakeSource(rows), client, store, file_store, settings, monkeypatch, recheck=True).new_count == 1
    assert store.by_key("1").latest_version == 2


def test_detail_limit_leaves_rest_pending(client, store, file_store, settings, monkeypatch):
    rows = [(str(i), f"제{i}차 국민임대 입주자 모집공고", date(2026, 10, i)) for i in range(1, 6)]
    pages(client, rows)
    limited = settings.__class__(**{**settings.__dict__, "detail_limit": 2})
    run(FakeSource(rows), client, store, file_store, limited, monkeypatch)
    assert sorted(p.status for p in store.posts.values()) == ["DONE", "DONE", "PENDING", "PENDING", "PENDING"]
    assert store.boards[("dcco", "43")].last_list_hash == ""  # 밀린 글이 있으면 목록 해시를 저장하지 않아요


def test_broken_detail_marks_failed_and_continues(client, store, file_store, settings, monkeypatch):
    rows = ROWS[:1] + [("5", "2026년 국민임대 입주자 모집공고", date(2026, 10, 5))]
    pages(client, rows)
    client.pages["https://a.kr/view?id=5"] = "BROKEN"
    result = run(FakeSource(rows), client, store, file_store, settings, monkeypatch)
    assert store.by_key("5").status == "FAILED" and store.by_key("1").status == "DONE"
    assert result.status == "SUCCESS" and any("상세를 읽지 못했어요" in w for w in result.warnings)


def test_blocked_stops_source_and_counts_against_the_post(client, store, file_store, settings, monkeypatch):
    """403·429면 출처 회차를 멈추고 그 글의 실패로 세요. 다음 회차엔 밀린 다른 글이 먼저 열리고, 3번 막힌 글은 더 열지 않아요.
    예전엔 그 글이 PENDING으로 남아 매 회차 먼저 열려 출처 전체가 멈춰 있었어요 (2026-11-10 코드 검토)."""
    rows = [("5", "2026년 국민임대 입주자 모집공고", date(2026, 10, 5)), ROWS[0]]
    pages(client, rows)
    client.pages["https://a.kr/view?id=5"] = BlockedError("HTTP 403")
    result = run(FakeSource(rows), client, store, file_store, settings, monkeypatch)
    assert result.status == "BLOCKED" and store.by_key("5").status == "FAILED" and store.by_key("5").attempts == 1
    assert store.by_key("1").status == "PENDING"  # 막힌 글이 먼저라 이번엔 못 열었어요

    result = run(FakeSource(rows), client, store, file_store, settings, monkeypatch)
    assert result.status == "BLOCKED" and store.by_key("1").status == "DONE" and store.by_key("5").attempts == 2

    run(FakeSource(rows), client, store, file_store, settings, monkeypatch)
    assert store.by_key("5").attempts == MAX_ATTEMPTS
    client.requested.clear()
    result = run(FakeSource(rows), client, store, file_store, settings, monkeypatch)
    assert result.status == "SUCCESS" and "https://a.kr/view?id=5" not in client.requested

    # 새벽 정정 확인은 횟수를 다 쓴 글도 하루 한 번 다시 열어요(2026-11-10 재검토: 상세만 3번 막힌 새 글은 영영 모이지 않았음)
    client.pages["https://a.kr/view?id=5"] = "본문"
    run(FakeSource(rows), client, store, file_store, settings, monkeypatch, recheck=True)
    assert "https://a.kr/view?id=5" in client.requested and store.by_key("5").latest_version == 1 and store.by_key("5").attempts == 0


def test_flaky_attachment_does_not_make_a_version_without_it(client, store, file_store, settings, monkeypatch):
    """첨부를 잠시 못 받으면 그 파일 없이 새 버전을 만들지 않아요(해시가 바뀌어 추출·알림이 다시 돌고 다음 회차에 되돌아갔음, 2026-11-10 코드 검토).
    실패로 세어 다음 회차에 다시 받고, 마지막 시도엔 이전 버전의 같은 첨부를 이어 써요: 본문이 그대로면 새 버전이 아니고, 본문이 바뀌었으면
    그 정정은 새 버전이 돼요(재검토: 이전 버전이 있으면 늘 건너뛰어 첨부가 계속 안 받아지면 본문 정정이 영영 반영되지 않았음).
    처음 글은 마지막 시도엔 그 파일 없이라도 저장해요."""
    rows = ROWS[:1]
    pages(client, rows)
    run(FakeSource(rows), client, store, file_store, settings, monkeypatch)
    client.files["https://a.kr/f/1.pdf"] = httpx.ConnectError("연결 끊김")
    result = run(FakeSource(rows), client, store, file_store, settings, monkeypatch, recheck=True)
    assert result.new_count == 0 and store.by_key("1").latest_version == 1
    assert (store.by_key("1").status, store.by_key("1").attempts) == ("FAILED", 1)
    assert any("이전 버전은 그대로 둬요" in w for w in result.warnings)
    assert run(FakeSource(rows), client, store, file_store, settings, monkeypatch).new_count == 0
    result = run(FakeSource(rows), client, store, file_store, settings, monkeypatch)  # 마지막 시도: 본문 그대로
    assert result.new_count == 0 and any("이전 버전의 같은 첨부를 이어 써요" in w for w in result.warnings)
    assert (store.by_key("1").status, store.by_key("1").attempts, store.by_key("1").latest_version) == ("DONE", 0, 1)  # 실패 횟수도 되돌림

    client.pages["https://a.kr/view?id=1"] = "정정된 본문"
    for _ in range(MAX_ATTEMPTS - 1):
        assert run(FakeSource(rows), client, store, file_store, settings, monkeypatch, recheck=True).new_count == 0
    assert run(FakeSource(rows), client, store, file_store, settings, monkeypatch).new_count == 1  # 마지막 시도: 정정된 본문 + 이전 공고문
    first, second = store.versions[0], store.versions[-1]
    assert second.body_text == "정정된 본문" and second.files[0].s3_key == first.files[0].s3_key
    assert second.files[0].file_hash == first.files[0].file_hash and second.files[0].text == first.files[0].text

    new = [("7", "2026년 국민임대 입주자 모집공고", date(2026, 10, 7))]
    pages(client, new)
    client.files["https://a.kr/f/7.pdf"] = httpx.ConnectError("연결 끊김")
    for attempt in range(1, MAX_ATTEMPTS):
        assert run(FakeSource(new), client, store, file_store, settings, monkeypatch).new_count == 0
        assert (store.by_key("7").status, store.by_key("7").attempts) == ("FAILED", attempt)
    assert run(FakeSource(new), client, store, file_store, settings, monkeypatch).new_count == 1  # 마지막 시도
    assert store.events[-1]["payload"]["files"] == []


def test_old_posts_are_not_opened(client, store, file_store, settings, monkeypatch):
    rows = [("9", "2024년 국민임대 입주자 모집공고", date(2024, 1, 1))]
    pages(client, rows)
    run(FakeSource(rows), client, store, file_store, settings, monkeypatch)
    assert store.by_key("9").status == "SKIPPED" and "365일" in store.by_key("9").last_error


def test_empty_list_counts_towards_structure_alert(client, store, file_store, settings, monkeypatch):
    pages(client, [])
    for _ in range(3):
        result = run(FakeSource([]), client, store, file_store, settings, monkeypatch)
    assert store.boards[("dcco", "43")].empty_runs == 3 and "구조 변경 의심" in result.warnings[-1]


def test_unclear_notice_file_leaves_warning(client, store, file_store, settings, monkeypatch):
    class UnnamedFiles(FakeSource):
        def parse_detail(self, item, body):
            files = [FileRef("붙임1 신청자격.pdf", "https://a.kr/f/a.pdf", 1), FileRef("2026 행복주택.pdf", "https://a.kr/f/b.pdf", 2)]
            return Detail(item.title, body, files)

    rows = ROWS[:1]
    pages(client, rows)
    client.files["https://a.kr/f/a.pdf"] = client.files["https://a.kr/f/b.pdf"] = b"%PDF-1.4 fake"
    result = run(UnnamedFiles(rows), client, store, file_store, settings, monkeypatch)
    assert result.new_count == 1 and any("첨부 순서로 골랐어요 (붙임1 신청자격.pdf)" in w for w in result.warnings)


class RegionSource(FakeSource):
    def parse_detail(self, item, body):
        detail = super().parse_detail(item, body)
        detail.meta = {"유형": "국민임대", "_raw": {"응답": "원본 그대로"}}
        detail.region_code = "11110"
        return detail


def test_region_code_goes_to_event_and_underscore_meta_stays_out_of_ai_text(client, store, file_store, settings, monkeypatch):
    rows = ROWS[:1]
    pages(client, rows)
    run(RegionSource(rows), client, store, file_store, settings, monkeypatch)
    [version] = store.versions
    assert store.events[0]["payload"]["regionCode"] == "11110"
    assert "유형: 국민임대" in version.full_text and "원본 그대로" not in version.full_text
    assert version.meta["_raw"] == {"응답": "원본 그대로"}  # 원본은 DB(raw_post_versions.meta)에는 남아요


def test_source_can_bring_its_own_client(settings):
    from mujuthaek_collector.__main__ import make_client
    from mujuthaek_collector.core.http_client import PoliteClient

    class OwnClientSource(FakeSource):
        def make_client(self, settings):
            return "출처 전용 클라이언트"

    assert make_client(OwnClientSource([]), settings) == "출처 전용 클라이언트"
    default = make_client(FakeSource([]), settings)
    assert isinstance(default, PoliteClient)
    default.close()


class ListBodySource(FakeSource):
    """본문을 목록 JSON에 싣는 출처(청년안심주택처럼): 상세는 목록 줄의 본문으로 만들어요."""

    def __init__(self, rows, bodies):
        super().__init__(rows)
        self.bodies = bodies  # post_key → 목록에 실린 본문

    def parse_list(self, board, body, page_url):
        items = super().parse_list(board, body, page_url)
        return [ListItem(i.board, i.post_key, i.title, i.posted_on, i.detail_url, meta={"content": self.bodies[i.post_key]}) for i in items]

    def parse_detail(self, item, body):
        return Detail(item.title, item.meta["content"], [FileRef("모집공고문.pdf", f"https://a.kr/f/{item.post_key}.pdf", 1)])


def test_a_body_carried_in_the_list_is_refreshed_when_the_post_is_listed_again(client, store, file_store, settings, monkeypatch):
    """2026-11-10 코드 검토: 상세 처리가 처음 본 목록 줄을 계속 써서, 본문을 목록에만 싣는 출처는 게시글 본문을 고쳐도 새 버전이 되지 않았어요."""
    rows = ROWS[:1]
    pages(client, rows)
    source = ListBodySource(rows, {"1": "청약신청 : 26.10.19 ~ 10.20"})
    run(source, client, store, file_store, settings, monkeypatch)
    source.bodies["1"] = "청약신청 : 26.10.19 ~ 10.27 (연장)"
    assert run(source, client, store, file_store, settings, monkeypatch, recheck=True).new_count == 1
    assert store.versions[-1].body_text == "청약신청 : 26.10.19 ~ 10.27 (연장)"
