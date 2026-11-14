"""수집 DB 저장. 파이프라인은 Store 규격만 알고, 운영은 PostgresStore, 테스트는 MemoryStore(tests/fakes.py)를 써요.

- 글(raw_posts)은 목록에서 본 순간 한 번 저장하고, 상태(SKIPPED·PENDING·DONE·FAILED, 처음 수집 개수 제한의 HELD·IGNORED)만 바꿔요
- 새 버전은 save_version 한 번의 트랜잭션으로 저장해요: 버전 + 첨부 + 추출 글자 + 글 상태 + 아웃박스 이벤트
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Protocol
from uuid import UUID

from mujuthaek_collector.core.files import FileRef
from mujuthaek_platform import outbox
from mujuthaek_platform.ids import uuid7

MAX_ATTEMPTS = 3  # FAILED 글은 3번까지 다시 시도
ORPHAN_FOLLOW_UP = "원래 모집공고를 찾지 못한 후속 안내"  # 등록할 때 원공고가 아직 없던 후속 안내(목록 읽기 뒤 다시 찾음)

SKIPPED, PENDING, DONE, FAILED = "SKIPPED", "PENDING", "DONE", "FAILED"
# 처음 수집 개수 제한 (core/intake.py): 고르기 전까지 기다리는 글, 고를 때 빠져 쓰지 않는 글 (다시 큐에 넣지 않아요)
HELD, IGNORED = "HELD", "IGNORED"


@dataclass
class Intake:
    """묶음의 처음 수집 고르기 결과. cutoff_on보다 오래된 새 글은 쓰지 않아요 (비어 있으면 기준일 없음)."""

    cutoff_on: date | None = None


@dataclass
class PostRow:
    id: UUID
    source_code: str
    board_key: str
    post_key: str
    kind: str
    title: str
    posted_on: date | None
    detail_url: str | None
    list_item: dict[str, Any]
    status: str
    attempts: int = 0
    last_error: str | None = None
    list_status: str | None = None
    deadline_on: date | None = None
    parent_post_id: UUID | None = None
    latest_version: int = 0


@dataclass
class BoardState:
    last_list_hash: str = ""
    empty_runs: int = 0


@dataclass
class SavedFile:
    idx: int
    name: str
    role: str  # NOTICE_DOC, UNIT_LIST
    download_url: str
    file_hash: str
    size_bytes: int
    s3_key: str | None
    stored_until: date
    text_status: str | None = None
    text: str | None = None  # 이 파일에서 뽑은 글자 (raw_texts)

    def as_event_file(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "file_type": FileRef(self.name, "", 0).ext,
            "role": self.role,
            "s3_key": self.s3_key,
            "download_url": self.download_url,
            "file_hash": self.file_hash,
        }


@dataclass
class NewVersion:
    post: PostRow
    version: int
    content_hash: str
    body_text: str
    meta: dict[str, Any]
    full_text: str
    run_id: UUID | None
    files: list[SavedFile] = field(default_factory=list)
    event: dict[str, Any] | None = None


class Store(Protocol):
    # 수집 회차
    def start_run(self, source_code: str) -> UUID: ...
    def finish_run(self, run_id: UUID, status: str, new_count: int, warnings: list[str]) -> None: ...
    # 게시판 상태
    def board_state(self, source_code: str, board_key: str) -> BoardState: ...
    def save_board_state(self, source_code: str, board_key: str, state: BoardState) -> None: ...
    # 글
    def find_post(self, source_code: str, post_key: str) -> PostRow | None: ...
    def insert_post(self, post: PostRow) -> None: ...
    def update_list_fields(self, post_id: UUID, list_status: str | None, deadline_on: date | None, list_item: dict[str, Any] | None = None) -> None: ...
    def set_parent(self, post_id: UUID, parent_post_id: UUID) -> None: ...
    def queued_posts(self, source_code: str, board_key: str, limit: int) -> list[PostRow]: ...
    def notices_posted_on(self, source_code: str, posted_on: date) -> list[PostRow]: ...
    def recent_notices(self, source_code: str, limit: int = 300) -> list[PostRow]: ...
    def requeue_open_posts(self, source_code: str, today: date, since_days: int) -> int: ...
    def orphan_follow_ups(self, source_code: str, since: date) -> list[PostRow]: ...
    def link_follow_up(self, post_id: UUID, parent_post_id: UUID, status: str, reason: str | None) -> None: ...
    def latest_hash(self, post_id: UUID) -> tuple[int, str] | None: ...
    def latest_files(self, post_id: UUID) -> list[SavedFile]: ...
    def mark_done(self, post_id: UUID) -> None: ...
    def mark_failed(self, post_id: UUID, error: str) -> None: ...
    def save_version(self, new: NewVersion) -> None: ...
    # 처음 수집 개수 제한: 고르기 전이면 None
    def intake(self, group: str) -> Intake | None: ...
    # 보관 기한 정리
    def expired_files(self, today: date, limit: int = 500) -> list[tuple[UUID, str]]: ...
    def mark_file_deleted(self, file_id: UUID) -> None: ...


POST_COLUMNS = (
    "id, source_code, board_key, post_key, kind, title, posted_on, detail_url, list_item, status, attempts, "
    "last_error, list_status, deadline_on, parent_post_id, latest_version"
)


def _row_to_post(row) -> PostRow:
    values = list(row)
    if isinstance(values[8], str):
        values[8] = json.loads(values[8])
    return PostRow(*values)


class PostgresStore:
    """collector 데이터베이스 테이블에 저장해요. 연결은 autocommit이고, 여러 문장은 transaction()으로 묶어요."""

    def __init__(self, db_url: str):
        from mujuthaek_platform import db

        self.conn = db.connect(db_url)
        self.conn.autocommit = True

    def close(self) -> None:
        self.conn.close()

    @staticmethod
    def _json(value: Any):
        from psycopg.types.json import Jsonb

        return Jsonb(value)

    # ── 수집 회차 ──────────────────────────────────────────────
    def start_run(self, source_code: str) -> UUID:
        run_id = uuid7()
        self.conn.execute("insert into crawl_runs (id, source_code) values (%s, %s)", (run_id, source_code))
        return run_id

    def finish_run(self, run_id: UUID, status: str, new_count: int, warnings: list[str]) -> None:
        self.conn.execute(
            "update crawl_runs set finished_at = now(), status = %s, new_count = %s, error = %s where id = %s",
            (status, new_count, "\n".join(warnings)[:10000] or None, run_id),
        )

    # ── 처음 수집 개수 제한 ────────────────────────────────────
    def intake(self, group: str) -> Intake | None:
        row = self.conn.execute("select cutoff_on from intake_decisions where group_code = %s", (group,)).fetchone()
        return Intake(row[0]) if row else None

    # ── 게시판 상태 ────────────────────────────────────────────
    def board_state(self, source_code: str, board_key: str) -> BoardState:
        row = self.conn.execute(
            "select last_list_hash, empty_runs from source_boards where source_code = %s and board_key = %s", (source_code, board_key)
        ).fetchone()
        return BoardState(*row) if row else BoardState()

    def save_board_state(self, source_code: str, board_key: str, state: BoardState) -> None:
        self.conn.execute(
            "insert into source_boards (source_code, board_key, last_list_hash, empty_runs, last_run_at) values (%s, %s, %s, %s, now()) "
            "on conflict (source_code, board_key) do update set last_list_hash = excluded.last_list_hash, "
            "empty_runs = excluded.empty_runs, last_run_at = now()",
            (source_code, board_key, state.last_list_hash, state.empty_runs),
        )

    # ── 글 ─────────────────────────────────────────────────────
    def find_post(self, source_code: str, post_key: str) -> PostRow | None:
        row = self.conn.execute(f"select {POST_COLUMNS} from raw_posts where source_code = %s and post_key = %s", (source_code, post_key)).fetchone()
        return _row_to_post(row) if row else None

    def insert_post(self, post: PostRow) -> None:
        self.conn.execute(
            "insert into raw_posts (id, source_code, board_key, post_key, kind, title, posted_on, detail_url, list_item, status, "
            "last_error, list_status, deadline_on, parent_post_id) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
            "on conflict (source_code, post_key) do nothing",
            (
                post.id,
                post.source_code,
                post.board_key,
                post.post_key,
                post.kind,
                post.title,
                post.posted_on,
                post.detail_url,
                self._json(post.list_item),
                post.status,
                post.last_error,
                post.list_status,
                post.deadline_on,
                post.parent_post_id,
            ),
        )

    def update_list_fields(self, post_id: UUID, list_status: str | None, deadline_on: date | None, list_item: dict[str, Any] | None = None) -> None:
        """목록에서 다시 본 글의 목록 값을 고쳐요. list_item(목록 한 줄 전체)도 새로 둬, 상세 처리가 처음 본 목록 값을 계속 쓰지 않게 해요
        (2026-11-10 코드 검토: 청년안심주택은 본문을 목록 JSON에서만 만들어 게시글 본문을 고쳐도 새 버전이 되지 않았음)."""
        item = self._json(list_item) if list_item is not None else None
        self.conn.execute(
            "update raw_posts set list_status = coalesce(%s, list_status), deadline_on = coalesce(%s, deadline_on), "
            "list_item = coalesce(%s::jsonb, list_item), updated_at = now() "
            "where id = %s and (list_status is distinct from %s or deadline_on is distinct from %s "
            "or list_item is distinct from coalesce(%s::jsonb, list_item))",
            (list_status, deadline_on, item, post_id, list_status, deadline_on, item),
        )

    def set_parent(self, post_id: UUID, parent_post_id: UUID) -> None:
        self.conn.execute("update raw_posts set parent_post_id = %s, updated_at = now() where id = %s", (parent_post_id, post_id))

    def queued_posts(self, source_code: str, board_key: str, limit: int) -> list[PostRow]:
        rows = self.conn.execute(
            f"select {POST_COLUMNS} from raw_posts where source_code = %s and board_key = %s "
            "and (status = 'PENDING' or (status = 'FAILED' and attempts < %s)) "
            "order by (status = 'PENDING') desc, posted_on desc nulls last, created_at limit %s",
            (source_code, board_key, MAX_ATTEMPTS, limit),
        ).fetchall()
        return [_row_to_post(r) for r in rows]

    def notices_posted_on(self, source_code: str, posted_on: date) -> list[PostRow]:
        rows = self.conn.execute(
            f"select {POST_COLUMNS} from raw_posts where source_code = %s and kind = 'NOTICE' and posted_on = %s", (source_code, posted_on)
        ).fetchall()
        return [_row_to_post(r) for r in rows]

    def recent_notices(self, source_code: str, limit: int = 300) -> list[PostRow]:
        rows = self.conn.execute(
            f"select {POST_COLUMNS} from raw_posts where source_code = %s and kind = 'NOTICE' order by posted_on desc nulls last limit %s",
            (source_code, limit),
        ).fetchall()
        return [_row_to_post(r) for r in rows]

    def requeue_open_posts(self, source_code: str, today: date, since_days: int) -> int:
        """새벽 정정 확인: 아직 마감 전이거나 마감일을 모르는 최근 공고를 PENDING으로 돌려 다시 열어봐요.
        다시 시도 횟수(MAX_ATTEMPTS)를 다 쓴 FAILED 글도 하루 한 번 다시 열어요(횟수는 그대로라 실패하면 다음 날까지 쉬어요).
        예전엔 DONE만 돌려, 가끔 막히는 글이 실패 3번을 채우면 정정 확인에서 빠지고 처음 글은 영영 모이지 않았어요(2026-11-10 재검토)."""
        cursor = self.conn.execute(
            "update raw_posts set status = 'PENDING', updated_at = now() where source_code = %s "
            "and (status = 'DONE' or (status = 'FAILED' and attempts >= %s)) "
            "and kind in ('NOTICE', 'CORRECTION') and (deadline_on is null or deadline_on >= %s) "
            "and (posted_on is null or posted_on >= %s)",
            (source_code, MAX_ATTEMPTS, today, date.min if since_days < 0 else today - timedelta(days=min(since_days, 90))),
        )
        return cursor.rowcount

    def orphan_follow_ups(self, source_code: str, since: date) -> list[PostRow]:
        """원공고를 찾지 못해 SKIPPED로 둔 최근 후속 안내(since 이후 게시, 게시일 모르면 포함)."""
        rows = self.conn.execute(
            f"select {POST_COLUMNS} from raw_posts where source_code = %s and kind = 'FOLLOW_UP' and status = 'SKIPPED' "
            "and parent_post_id is null and last_error = %s and (posted_on is null or posted_on >= %s)",
            (source_code, ORPHAN_FOLLOW_UP, since),
        ).fetchall()
        return [_row_to_post(r) for r in rows]

    def link_follow_up(self, post_id: UUID, parent_post_id: UUID, status: str, reason: str | None) -> None:
        self.conn.execute(
            "update raw_posts set parent_post_id = %s, status = %s, last_error = %s, updated_at = now() "
            "where id = %s and status = 'SKIPPED' and parent_post_id is null",
            (parent_post_id, status, reason, post_id),
        )

    def latest_hash(self, post_id: UUID) -> tuple[int, str] | None:
        row = self.conn.execute(
            "select version, content_hash from raw_post_versions where raw_post_id = %s order by version desc limit 1", (post_id,)
        ).fetchone()
        return (row[0], row[1]) if row else None

    def latest_files(self, post_id: UUID) -> list[SavedFile]:
        """마지막 버전의 첨부(원본이 남아 있는 것)와 그 글자. 첨부를 끝내 받지 못할 때 이전 것을 이어 쓰는 데 써요."""
        rows = self.conn.execute(
            "select f.idx, f.name, f.role, f.download_url, f.file_hash, f.size_bytes, f.s3_key, f.stored_until, f.text_status, t.text "
            "from raw_files f join raw_post_versions v on v.id = f.version_id left join raw_texts t on t.file_id = f.id "
            "where v.raw_post_id = %s and v.version = (select max(version) from raw_post_versions where raw_post_id = %s) "
            "and f.s3_key is not null and f.deleted_at is null order by f.idx",
            (post_id, post_id),
        ).fetchall()
        return [SavedFile(*row) for row in rows]

    def mark_done(self, post_id: UUID) -> None:
        # 실패 횟수도 되돌려요: 남겨 두면 가끔 실패하는 글이 날을 넘겨 횟수를 채워 다시 시도 대상에서 빠졌어요(2026-11-10 재검토)
        self.conn.execute("update raw_posts set status = 'DONE', attempts = 0, last_error = null, updated_at = now() where id = %s", (post_id,))

    def mark_failed(self, post_id: UUID, error: str) -> None:
        self.conn.execute(
            "update raw_posts set status = 'FAILED', attempts = attempts + 1, last_error = %s, updated_at = now() where id = %s",
            (error[:2000], post_id),
        )

    def save_version(self, new: NewVersion) -> None:
        version_id = uuid7()
        with self.conn.transaction(), self.conn.cursor() as cur:
            cur.execute(
                "insert into raw_post_versions (id, raw_post_id, version, content_hash, body_text, meta, full_text, crawl_run_id) "
                "values (%s, %s, %s, %s, %s, %s, %s, %s)",
                (version_id, new.post.id, new.version, new.content_hash, new.body_text, self._json(new.meta), new.full_text, new.run_id),
            )
            for f in new.files:
                file_id = uuid7()
                cur.execute(
                    "insert into raw_files (id, version_id, idx, name, role, download_url, file_hash, size_bytes, s3_key, stored_until, text_status) "
                    "values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (file_id, version_id, f.idx, f.name, f.role, f.download_url, f.file_hash, f.size_bytes, f.s3_key, f.stored_until, f.text_status),
                )
                if f.text:
                    cur.execute("insert into raw_texts (id, file_id, text) values (%s, %s, %s)", (uuid7(), file_id, f.text))
            cur.execute(
                "update raw_posts set status = 'DONE', latest_version = %s, attempts = 0, last_error = null, updated_at = now() where id = %s",
                (new.version, new.post.id),
            )
            if new.event is not None:
                outbox.add(cur, new.event)

    # ── 보관 기한 정리 ─────────────────────────────────────────
    def expired_files(self, today: date, limit: int = 500) -> list[tuple[UUID, str]]:
        rows = self.conn.execute(
            "select id, s3_key from raw_files where stored_until < %s and s3_key is not null and deleted_at is null limit %s", (today, limit)
        ).fetchall()
        return [(r[0], r[1]) for r in rows]

    def mark_file_deleted(self, file_id: UUID) -> None:
        self.conn.execute("update raw_files set s3_key = null, deleted_at = now() where id = %s", (file_id,))
