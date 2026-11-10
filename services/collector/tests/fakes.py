"""테스트용 가짜 부품. 실제 DB·S3·기관 사이트 없이 파이프라인 전체를 돌려볼 수 있어요."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date
from uuid import UUID

from mujuthaek_collector.core.storage import MAX_ATTEMPTS, ORPHAN_FOLLOW_UP, BoardState, Intake, NewVersion, PostRow
from mujuthaek_collector.errors import FileRejected
from mujuthaek_platform.ids import uuid7


@dataclass
class MemoryStore:
    """core.storage.Store 규격을 메모리로 구현해요. 저장된 버전·이벤트를 그대로 꺼내 볼 수 있어요."""

    runs: dict[UUID, dict] = field(default_factory=dict)
    boards: dict[tuple[str, str], BoardState] = field(default_factory=dict)
    posts: dict[UUID, PostRow] = field(default_factory=dict)
    versions: list[NewVersion] = field(default_factory=list)
    deleted_files: list[UUID] = field(default_factory=list)
    # 처음 수집 개수 제한: 묶음별 고른 결과. 기본은 모두 고른 것(기준일 없음)이라 지금처럼 동작해요. None이면 고르기 전
    intakes: dict[str, Intake | None] = field(default_factory=dict)

    @property
    def events(self) -> list[dict]:
        return [v.event for v in self.versions if v.event]

    def by_key(self, post_key: str) -> PostRow:
        return next(p for p in self.posts.values() if p.post_key == post_key)

    def intake(self, group):
        return self.intakes.get(group, Intake())

    def start_run(self, source_code):
        run_id = uuid7()
        self.runs[run_id] = {"source": source_code, "status": "RUNNING"}
        return run_id

    def finish_run(self, run_id, status, new_count, warnings):
        self.runs[run_id].update(status=status, new_count=new_count, warnings=list(warnings))

    def board_state(self, source_code, board_key):
        return replace(self.boards.get((source_code, board_key), BoardState()))

    def save_board_state(self, source_code, board_key, state):
        self.boards[(source_code, board_key)] = replace(state)

    def find_post(self, source_code, post_key):
        return next((p for p in self.posts.values() if p.source_code == source_code and p.post_key == post_key), None)

    def insert_post(self, post):
        if self.find_post(post.source_code, post.post_key) is None:
            self.posts[post.id] = post

    def update_list_fields(self, post_id, list_status, deadline_on, list_item=None):
        post = self.posts[post_id]
        post.list_status = list_status or post.list_status
        post.deadline_on = deadline_on or post.deadline_on
        post.list_item = list_item if list_item is not None else post.list_item

    def set_parent(self, post_id, parent_post_id):
        self.posts[post_id].parent_post_id = parent_post_id

    def queued_posts(self, source_code, board_key, limit):
        queued = [
            p
            for p in self.posts.values()
            if p.source_code == source_code and p.board_key == board_key and (p.status == "PENDING" or (p.status == "FAILED" and p.attempts < MAX_ATTEMPTS))
        ]
        queued.sort(key=lambda p: (p.status != "PENDING", -(p.posted_on or date.min).toordinal()))
        return queued[:limit]

    def notices_posted_on(self, source_code, posted_on):
        return [p for p in self.posts.values() if p.source_code == source_code and p.kind == "NOTICE" and p.posted_on == posted_on]

    def recent_notices(self, source_code, limit=300):
        notices = [p for p in self.posts.values() if p.source_code == source_code and p.kind == "NOTICE"]
        return sorted(notices, key=lambda p: p.posted_on or date.min, reverse=True)[:limit]

    def requeue_open_posts(self, source_code, today, since_days):
        count = 0
        for p in self.posts.values():
            exhausted = p.status == "FAILED" and p.attempts >= MAX_ATTEMPTS
            if (
                p.source_code == source_code
                and (p.status == "DONE" or exhausted)
                and p.kind in ("NOTICE", "CORRECTION")
                and (p.deadline_on is None or p.deadline_on >= today)
            ):
                p.status, count = "PENDING", count + 1
        return count

    def orphan_follow_ups(self, source_code, since):
        return [
            p
            for p in self.posts.values()
            if p.source_code == source_code
            and p.kind == "FOLLOW_UP"
            and p.status == "SKIPPED"
            and p.parent_post_id is None
            and p.last_error == ORPHAN_FOLLOW_UP
            and (p.posted_on is None or p.posted_on >= since)
        ]

    def link_follow_up(self, post_id, parent_post_id, status, reason):
        post = self.posts[post_id]
        if post.status == "SKIPPED" and post.parent_post_id is None:
            post.parent_post_id, post.status, post.last_error = parent_post_id, status, reason

    def latest_hash(self, post_id):
        mine = [v for v in self.versions if v.post.id == post_id]
        return (mine[-1].version, mine[-1].content_hash) if mine else None

    def latest_files(self, post_id):
        mine = [v for v in self.versions if v.post.id == post_id]
        return [replace(f) for f in mine[-1].files if f.s3_key] if mine else []

    def mark_done(self, post_id):
        post = self.posts[post_id]
        post.status, post.attempts, post.last_error = "DONE", 0, None

    def mark_failed(self, post_id, error):
        post = self.posts[post_id]
        post.status, post.attempts, post.last_error = "FAILED", post.attempts + 1, error

    def save_version(self, new):
        self.versions.append(new)
        post = self.posts[new.post.id]
        post.status, post.latest_version, post.attempts, post.last_error = "DONE", new.version, 0, None

    def expired_files(self, today, limit=500):
        return []

    def mark_file_deleted(self, file_id):
        self.deleted_files.append(file_id)


@dataclass
class MemoryFileStore:
    objects: dict[str, bytes] = field(default_factory=dict)
    metadatas: dict[str, dict[str, str]] = field(default_factory=dict)

    def put(self, key, data, content_type):
        self.objects[key] = data
        return key

    def delete(self, key):
        self.objects.pop(key, None)
        self.metadatas.pop(key, None)

    def put_file(self, key, path, content_type, metadata):
        self.objects[key] = path.read_bytes()
        self.metadatas[key] = dict(metadata)
        return key

    def metadata(self, key):
        return self.metadatas.get(key) if key in self.objects else None


@dataclass
class FakeClient:
    """주소 → 응답 표. 등록 안 된 주소를 요청하면 테스트가 실패해서, 수집기가 어떤 주소를 부르는지 확인돼요."""

    pages: dict[str, str] = field(default_factory=dict)
    files: dict[str, bytes] = field(default_factory=dict)
    rejected: set[str] = field(default_factory=set)
    requested: list[str] = field(default_factory=list)

    def text(self, url, *, data=None, referer=None):
        self.requested.append(url)
        if url not in self.pages:
            raise AssertionError(f"예상하지 않은 요청: {url}")
        page = self.pages[url]
        if isinstance(page, Exception):
            raise page
        return page

    def download(self, url, *, referer=None):
        self.requested.append(url)
        if url in self.rejected:
            raise FileRejected("robots.txt가 막은 주소")
        data = self.files[url]
        if isinstance(data, Exception):  # 받기 오류 흉내 (연결 끊김 등)
            raise data
        return data

    def close(self):
        pass
