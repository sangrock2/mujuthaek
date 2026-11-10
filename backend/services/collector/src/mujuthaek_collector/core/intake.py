"""처음 수집 개수 제한 (2026-10-27 결정). 배포 뒤 처음 한 번은 묶음마다 최신 N개만 AI 추출로 보내고, 그 이전 글은 쓰지 않아요.

묶음 (개수는 Settings.intake_limits, 환경 변수로 바꿔요)
  HOUSING_LH     LH 주거 공고                        10
  HOUSING_OTHER  LH 말고 다른 게시판 주거 공고 (합쳐서)  10
  SPACE          사업공간 모집 (정책 출처의 SPACE_RECRUITMENT)  10
  POLICY         지원 정책 (혜택·창업 지원, 출처 합쳐서)  500

흐름
  고르기 전   목록에서 처음 본 열 글을 PENDING 대신 HELD로 둬요 (상세를 열지 않아 AI도 돌지 않아요)
  고르기      decide: HELD 중 날짜가 최신인 N개 → PENDING, 나머지 → IGNORED. 고른 글 중 가장 오래된 날짜를 기준일로 남겨요
  고른 뒤     새 글은 바로 PENDING, 기준일보다 오래된 글은 IGNORED (늦게 읽힌 출처의 옛 글이 들어오지 않게)
IGNORED는 목록이 바뀌어도 다시 큐에 넣지 않아요. 고르는 때는 수집기가 뜰 때(처음 수집 직후)와 매일 정책 수집 뒤예요.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import Any

from mujuthaek_collector.core.storage import HELD, IGNORED, PENDING

log = logging.getLogger(__name__)

HOUSING_LH, HOUSING_OTHER, SPACE, POLICY = "HOUSING_LH", "HOUSING_OTHER", "SPACE", "POLICY"
GROUPS = (HOUSING_LH, HOUSING_OTHER, SPACE, POLICY)
DEFAULT_LIMITS = {HOUSING_LH: 10, HOUSING_OTHER: 10, SPACE: 10, POLICY: 500}
IGNORED_REASON = "처음 수집 개수 제한에서 빠진 이전 글이라 쓰지 않아요"

# 묶음마다 (테이블, 날짜 칸, 묶음 조건)
_TABLES = {
    HOUSING_LH: ("raw_posts", "posted_on", "source_code = 'lh'"),
    HOUSING_OTHER: ("raw_posts", "posted_on", "source_code <> 'lh'"),
    SPACE: ("raw_policies", "listed_on", "field = 'SPACE_RECRUITMENT'"),
    POLICY: ("raw_policies", "listed_on", "field <> 'SPACE_RECRUITMENT'"),
}


def post_group(source_code: str) -> str:
    return HOUSING_LH if source_code == "lh" else HOUSING_OTHER


def policy_group(field: str | None) -> str:
    return SPACE if field == "SPACE_RECRUITMENT" else POLICY


def open_status(store: Any, group: str, on: date | None) -> str:
    """열 글(PENDING이 될 글)을 지금 어떤 상태로 둘지: 고르기 전 HELD, 기준일보다 오래되면 IGNORED, 아니면 PENDING."""
    decided = store.intake(group)
    if decided is None:
        return HELD
    if decided.cutoff_on and on and on < decided.cutoff_on:
        return IGNORED
    return PENDING


@dataclass
class Decision:
    group: str
    limit: int
    kept: int
    ignored: int
    cutoff_on: date | None


def decide(conn: Any, limits: dict[str, int]) -> list[Decision]:
    """아직 고르지 않은 묶음 중 HELD 글이 있는 묶음을 골라요. HELD가 없으면(아직 아무것도 못 읽음) 다음 차례로 미뤄요."""
    decisions = []
    for group in GROUPS:
        table, day, where = _TABLES[group]
        limit = max(0, limits.get(group, DEFAULT_LIMITS[group]))
        with conn.transaction():
            # 같은 묶음을 두 곳에서 동시에 고르지 않게 (수집기가 뜰 때·매일 고르기)
            conn.execute("select pg_advisory_xact_lock(hashtext('intake:' || %s))", (group,))
            if conn.execute("select 1 from intake_decisions where group_code = %s", (group,)).fetchone():
                continue
            held = conn.execute(f"select count(*) from {table} where status = %s and {where}", (HELD,)).fetchone()[0]
            if not held:
                continue
            kept_days = conn.execute(
                f"update {table} set status = %s, updated_at = now() where id in ("
                f"select id from {table} where status = %s and {where} order by {day} desc nulls last, created_at desc limit %s) "
                f"returning {day}",
                (PENDING, HELD, limit),
            ).fetchall()
            ignored = conn.execute(
                f"update {table} set status = %s, last_error = %s, updated_at = now() where status = %s and {where}",
                (IGNORED, IGNORED_REASON, HELD),
            ).rowcount
            days = [d for (d,) in kept_days if d]
            cutoff = min(days) if days else None
            conn.execute(
                "insert into intake_decisions (group_code, limit_count, kept, ignored, cutoff_on) values (%s, %s, %s, %s, %s)",
                (group, limit, len(kept_days), ignored, cutoff),
            )
        decision = Decision(group, limit, len(kept_days), ignored, cutoff)
        log.info(
            "처음 수집 고르기",
            extra={"group": group, "limit": limit, "kept": decision.kept, "ignored": ignored, "cutoff": str(cutoff) if cutoff else None},
        )
        decisions.append(decision)
    return decisions


def undecided(conn: Any) -> list[str]:
    """아직 고르지 않은 묶음."""
    done = {row[0] for row in conn.execute("select group_code from intake_decisions").fetchall()}
    return [g for g in GROUPS if g not in done]


def summary(conn: Any) -> list[str]:
    """묶음마다 고른 결과 또는 기다리는 글 수 (명령줄 intake)."""
    rows = {
        g: (limit, kept, ignored, cutoff, at)
        for g, limit, kept, ignored, cutoff, at in conn.execute(
            "select group_code, limit_count, kept, ignored, cutoff_on, decided_at from intake_decisions"
        ).fetchall()
    }
    lines = []
    for group in GROUPS:
        if group in rows:
            limit, kept, ignored, cutoff, at = rows[group]
            if not limit and not kept and not ignored:
                lines.append(f"{group:14} 제한 없음 (이미 데이터가 있던 DB)")
            else:
                lines.append(f"{group:14} 골랐음 {at:%m-%d %H:%M}  남김 {kept}/{limit}  안 씀 {ignored}  기준일 {cutoff or '-'}")
        else:
            table, _, where = _TABLES[group]
            held = conn.execute(f"select count(*) from {table} where status = %s and {where}", (HELD,)).fetchone()[0]
            lines.append(f"{group:14} 고르기 전  기다리는 글 {held}")
    return lines
