"""게시판 출처를 출처마다 따로 수집: 느린 출처가 다른 출처를 막지 않고, 같은 출처만 겹치지 않아요 (2026-10-27)."""

import threading
from concurrent.futures import ThreadPoolExecutor

from mujuthaek_collector import __main__ as main
from mujuthaek_collector.core.locks import SourceLocks


class FakeSettings:
    parallel_sources = 3


def test_source_locks_only_block_the_same_source():
    locks = SourceLocks()
    assert locks.acquire("lh")
    assert not locks.acquire("lh")
    assert locks.acquire("sh")
    locks.release("lh")
    assert locks.acquire("lh")


def test_slow_source_does_not_hold_back_the_others(monkeypatch):
    release_lh = threading.Event()
    others_done = threading.Event()
    done: list[str] = []

    def collect(code, settings, *, recheck=False):
        if code == "lh":
            assert release_lh.wait(5)
        done.append(code)
        if {"sh", "gh"} <= set(done):
            others_done.set()

    monkeypatch.setattr(main, "enabled_sources", lambda settings, order=None: ["lh", "sh", "gh"])
    monkeypatch.setattr(main, "collect", collect)
    monkeypatch.setattr(main, "_locks", SourceLocks())
    pool = ThreadPoolExecutor(max_workers=3)
    try:
        main.collect_all(FakeSettings(), pool=pool)  # 맡기고 바로 돌아와요
        assert others_done.wait(5)  # lh가 아직 도는 중인데 sh · gh는 끝나요
        assert "lh" not in done

        # 다음 회차: 아직 도는 lh만 건너뛰고 나머지는 다시 돌아요
        main.collect_all(FakeSettings(), pool=pool)
        release_lh.set()
    finally:
        pool.shutdown(wait=True)
    assert done.count("lh") == 1
    assert done.count("sh") == 2 and done.count("gh") == 2


def test_run_all_without_pool_waits_for_every_source(monkeypatch):
    done: list[str] = []
    monkeypatch.setattr(main, "enabled_sources", lambda settings, order=None: ["lh", "sh"])
    monkeypatch.setattr(main, "collect", lambda code, settings, *, recheck=False: done.append(code))
    monkeypatch.setattr(main, "_locks", SourceLocks())
    main.collect_all(FakeSettings())
    assert sorted(done) == ["lh", "sh"]
