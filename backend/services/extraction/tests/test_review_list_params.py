"""검수 목록의 이어 받기·거르기 칸 검사(DB 없이). 실제 조회는 test_store_postgres.py에서 봅니다."""

from contextlib import contextmanager

from mujuthaek_extraction.review_api import ReviewService, _list_after, _page


class FakeStore:
    def __init__(self):
        self.calls = []

    def reviews(self, status, limit, reason, after):
        self.calls.append(("reviews", status, limit, reason, after))
        return [{"jobId": str(i)} for i in range(limit)]

    def review_count(self, status, reason):
        return 99

    def benefit_reviews(self, status, limit, reported, after):
        self.calls.append(("benefit_reviews", status, limit, reported, after))
        return []

    def benefit_review_count(self, status, reported):
        return 0


def service_with(store):
    @contextmanager
    def session():
        yield store

    return ReviewService(session, lambda *a: {})


def test_after_needs_both_time_and_id_in_valid_format():
    assert _list_after(None, None) is None
    assert _list_after("2026-10-29T11:52:16.012345+09:00", "01a182de-860a-7000-9aac-e9b588fe59df") == (
        "2026-10-29T11:52:16.012345+09:00",
        "01a182de-860a-7000-9aac-e9b588fe59df",
    )
    # 파이썬 str(datetime)처럼 띄어쓰기로 나눈 시각도 받아요(목록 응답의 queuedAt 그대로)
    assert _list_after("2026-10-29 11:52:16+09:00", "01a182de-860a-7000-9aac-e9b588fe59df")[0] == "2026-10-29T11:52:16+09:00"
    assert isinstance(_list_after("2026-10-29T11:52:16+09:00", None), str)
    assert isinstance(_list_after("어제", "01a182de-860a-7000-9aac-e9b588fe59df"), str)
    assert isinstance(_list_after("2026-10-29T11:52:16+09:00", "not-a-uuid"), str)


def test_page_reads_one_more_to_know_if_there_is_more():
    assert _page([1, 2, 3], 2) == ([1, 2], True)
    assert _page([1, 2], 2) == ([1, 2], False)


def test_list_passes_reason_and_cursor_and_reports_more():
    store = FakeStore()
    status, body = service_with(store).list("PENDING", "3", "CHECK", "2026-10-29T11:52:16+09:00", "01a182de-860a-7000-9aac-e9b588fe59df")
    assert status == 200 and len(body["items"]) == 3 and body["hasMore"] and body["total"] == 99
    assert store.calls == [("reviews", "PENDING", 4, "CHECK", ("2026-10-29T11:52:16+09:00", "01a182de-860a-7000-9aac-e9b588fe59df"))]
    assert service_with(store).list("PENDING", None, "NOPE")[0] == 400
    assert service_with(store).list("PENDING", None, None, "2026-10-29T11:52:16+09:00", None)[0] == 400


def test_benefit_list_reads_reported_flag():
    store = FakeStore()
    assert service_with(store).benefit_list("PENDING", "5", "true")[1] == {"items": [], "total": 0, "hasMore": False}
    assert store.calls == [("benefit_reviews", "PENDING", 6, True, None)]
    assert service_with(store).benefit_list("PENDING", None, "yes")[0] == 400
