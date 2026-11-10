"""처음 수집 개수 제한 (core/intake.py): 고르기 전 HELD, 고른 뒤 기준일보다 오래된 글 IGNORED, 고르기(decide)."""

import os
from dataclasses import replace
from datetime import date

import pytest

from mujuthaek_collector.core import intake
from mujuthaek_collector.core.storage import Intake, PostgresStore
from mujuthaek_collector.sources.policy.bizinfo import BizinfoSource
from mujuthaek_collector.sources.policy.gov24 import Gov24Source
from mujuthaek_collector.sources.policy.kstartup import KStartupSource
from tests import policy_samples as s
from tests.policy_fakes import PolicyMemoryStore, list_url
from tests.test_pipeline import ROWS, FakeSource, pages, run
from tests.test_policy_pipeline import KEY
from tests.test_policy_pipeline import run as run_policy


def test_board_posts_wait_before_intake_is_decided(client, store, file_store, settings, monkeypatch):
    store.intakes["HOUSING_OTHER"] = None  # 고르기 전
    pages(client, ROWS)
    result = run(FakeSource(ROWS), client, store, file_store, settings, monkeypatch)
    assert result.new_count == 0 and store.events == []
    assert store.by_key("1").status == "HELD"  # 모집공고는 상세를 열지 않고 기다려요
    assert store.by_key("3").status == "SKIPPED"  # 원래 안 여는 글은 그대로
    assert not any("view?id=" in url for url in client.requested)


def test_after_intake_posts_older_than_cutoff_are_not_used(client, store, file_store, settings, monkeypatch):
    store.intakes["HOUSING_OTHER"] = Intake(date(2026, 10, 5))
    rows = [*ROWS, ("5", "2026년 국민임대 입주자 모집공고", date(2026, 10, 12))]
    pages(client, rows)
    run(FakeSource(rows), client, store, file_store, settings, monkeypatch)
    assert store.by_key("1").status == "IGNORED"  # 10월 1일 → 기준일 전
    assert store.by_key("1").last_error == intake.IGNORED_REASON
    assert store.by_key("5").status == "DONE"  # 기준일 뒤 새 글은 바로 수집해요
    assert store.by_key("2").status == "IGNORED"  # 쓰지 않는 공고의 후속 안내도 쓰지 않아요
    assert [e["payload"]["title"] for e in store.events] == ["2026년 국민임대 입주자 모집공고"]


def test_lh_and_other_boards_are_separate_groups():
    assert intake.post_group("lh") == "HOUSING_LH" and intake.post_group("sh") == "HOUSING_OTHER"
    assert intake.policy_group("SPACE_RECRUITMENT") == "SPACE"
    assert intake.policy_group("BENEFIT") == intake.policy_group("STARTUP_SUPPORT") == "POLICY"


def test_policies_wait_and_ignored_ones_are_never_requeued(file_store, policy_settings_kstartup):
    api, web, policy_settings = policy_settings_kstartup
    store = PolicyMemoryStore(intakes={"POLICY": None})
    source = KStartupSource(KEY)
    api.pages[list_url(source)] = s.kstartup_list([s.KSTARTUP_POLICY])
    result = run_policy(source, api, web, store, file_store, policy_settings)
    held = store.by_key("179540")
    assert result.new_count == 0 and store.events == [] and held.status == "HELD"
    assert held.listed_on == date(2026, 10, 16)  # 접수 시작일

    held.status = "IGNORED"  # 고를 때 빠짐
    changed = {**s.KSTARTUP_POLICY, "biz_pbanc_nm": "제목이 바뀐 공고"}
    api.pages[list_url(source)] = s.kstartup_list([changed])
    store.intakes["POLICY"] = Intake()
    run_policy(source, api, web, store, file_store, policy_settings)
    assert store.by_key("179540").status == "IGNORED" and store.events == []


def test_listed_on_reads_each_source_date_format():
    assert BizinfoSource(KEY).listed_on({"creatPnttm": "2026-10-16 14:04:07"}) == date(2026, 10, 16)
    assert Gov24Source(KEY).listed_on({"등록일시": "20220822150443"}) == date(2022, 8, 22)
    assert KStartupSource(KEY).listed_on({"pbanc_rcpt_bgng_dt": ""}) is None
    assert KStartupSource(KEY).listed_on({"pbanc_rcpt_bgng_dt": "20261399"}) is None


@pytest.fixture
def policy_settings_kstartup(api, web, policy_settings):
    return api, web, replace(policy_settings, detail_limit=20)


@pytest.fixture
def api():
    from tests.fakes import FakeClient

    return FakeClient()


@pytest.fixture
def web():
    from tests.fakes import FakeClient

    return FakeClient()


@pytest.fixture
def policy_settings():
    from mujuthaek_collector.sources.policy.config import PolicySettings

    return PolicySettings(data_go_kr_key=KEY, youth_key=KEY, detail_limit=20, api_delay_seconds=0)


# ── 고르기: 실제 DB (로컬 collector_test가 있을 때만) ───────────────
DB_URL = os.getenv("COLLECTOR_TEST_DB_URL")


@pytest.mark.skipif(not DB_URL, reason="COLLECTOR_TEST_DB_URL이 없어요 (로컬 DB 테스트)")
def test_decide_keeps_latest_per_group_and_ignores_the_rest():
    store = PostgresStore(DB_URL)
    conn = store.conn
    try:
        conn.execute("truncate intake_decisions, outbox, raw_units, raw_texts, raw_files, raw_post_versions, raw_posts")
        conn.execute("truncate raw_policy_files, raw_policy_versions, raw_policies cascade")
        for n in range(5):  # LH 3건 + 다른 출처 2건
            code = "lh" if n < 3 else "sh"
            conn.execute(
                "insert into raw_posts (id, source_code, board_key, post_key, kind, title, posted_on, list_item, status) "
                "values (gen_random_uuid(), %s, 'b', %s, 'NOTICE', %s, %s, '{}', 'HELD')",
                (code, f"p{n}", f"공고 {n}", date(2026, 10, 1 + n)),
            )
        for n in range(4):  # 정책 4건 (하나는 등록일 모름)
            conn.execute(
                "insert into raw_policies (id, source_code, policy_id, title, marker, list_raw, status, field, listed_on) "
                "values (gen_random_uuid(), 'bizinfo', %s, %s, 'm', '{}', 'HELD', 'STARTUP_SUPPORT', %s)",
                (f"q{n}", f"정책 {n}", date(2026, 9, 1 + n) if n else None),
            )
        decisions = {d.group: d for d in intake.decide(conn, {"HOUSING_LH": 2, "HOUSING_OTHER": 10, "SPACE": 10, "POLICY": 2})}
        assert decisions["HOUSING_LH"].kept == 2 and decisions["HOUSING_LH"].ignored == 1
        assert decisions["HOUSING_LH"].cutoff_on == date(2026, 10, 2)
        assert decisions["HOUSING_OTHER"].kept == 2 and decisions["HOUSING_OTHER"].ignored == 0
        assert decisions["POLICY"].kept == 2 and decisions["POLICY"].cutoff_on == date(2026, 9, 3)
        assert "SPACE" not in decisions  # 읽은 글이 없으면 다음 차례로 미뤄요
        statuses = dict(conn.execute("select post_key, status from raw_posts").fetchall())
        assert statuses == {"p0": "IGNORED", "p1": "PENDING", "p2": "PENDING", "p3": "PENDING", "p4": "PENDING"}
        policies = dict(conn.execute("select policy_id, status from raw_policies").fetchall())
        assert policies == {"q0": "IGNORED", "q1": "IGNORED", "q2": "PENDING", "q3": "PENDING"}  # 등록일 모름은 뒤로
        assert intake.decide(conn, {}) == []  # 다시 불러도 이미 고른 묶음은 그대로
        assert intake.undecided(conn) == ["SPACE"]
        assert store.intake("HOUSING_LH") == Intake(date(2026, 10, 2)) and store.intake("SPACE") is None
    finally:
        conn.execute("truncate intake_decisions")
        store.close()
