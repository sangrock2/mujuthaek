"""Session ownership for source runs; only managed orphan records may be recovered."""

import hashlib
from uuid import UUID, uuid4

from mujuthaek_platform.ids import uuid7

INSTANCE = uuid4()
LOCK_NAMESPACE = 0x4D554A55
MAX_ORPHANS = 100
RECOVERY_REASON = "Previous managed collector session ended before completing the run"


def source_lock(code: str) -> tuple[int, int]:
    return LOCK_NAMESPACE, int.from_bytes(hashlib.sha256(code.encode()).digest()[:4], signed=True)


class SourceAlreadyRunning(RuntimeError):
    pass


class RunOwnership:
    def __init__(self, conn):
        self.conn = conn
        self.current: UUID | None = None
        self.key: tuple[int, int] | None = None

    def _release(self):
        key, self.key = self.key, None
        if key is not None and not self.conn.closed:
            self.conn.execute("select pg_advisory_unlock(%s, %s)", key)

    def start(self, code: str) -> UUID:
        if self.current is not None:
            raise SourceAlreadyRunning("This connection already owns a source run")
        key = source_lock(code)
        if not self.conn.execute("select pg_try_advisory_lock(%s, %s)", key).fetchone()[0]:
            raise SourceAlreadyRunning("Another database session owns this source run")
        self.key = key
        run_id = uuid7()
        try:
            with self.conn.transaction():
                # 잠금을 얻은 세션만 같은 출처의 managed 회차를 복구해요. legacy 기록은 보존합니다.
                old = self.conn.execute(
                    "select id from crawl_runs where source_code=%s and status='RUNNING' and finished_at is null "
                    "and owner_instance is not null order by started_at, id limit %s for update",
                    (code, MAX_ORPHANS + 1),
                ).fetchall()
                if len(old) > MAX_ORPHANS:
                    raise RuntimeError("Managed orphan scope exceeds automatic recovery limit")
                if old:
                    changed = self.conn.execute(
                        "update crawl_runs set status='FAILED', finished_at=now(), error=concat_ws(E'\\n',nullif(left(error,9800),''),%s) where id=any(%s)",
                        (RECOVERY_REASON, [row[0] for row in old]),
                    ).rowcount
                    if changed != len(old):
                        raise RuntimeError("Managed orphan scope changed")
                self.conn.execute("insert into crawl_runs (id, source_code, owner_instance) values (%s, %s, %s)", (run_id, code, INSTANCE))
        except BaseException:
            try:
                self._release()
            except Exception:
                self.conn.close()  # 연결을 종료하면 세션 잠금도 반납돼요.
            raise
        self.current = run_id
        return run_id

    def finish(self, run_id: UUID, status: str, new_count: int, warnings: list[str]):
        if self.current != run_id:
            raise RuntimeError("Run is not owned by this connection")
        try:
            with self.conn.transaction():
                changed = self.conn.execute(
                    "update crawl_runs set finished_at=now(), status=%s, new_count=%s, error=%s where id=%s and owner_instance=%s and status='RUNNING'",
                    (status, new_count, "\n".join(warnings)[:10000] or None, run_id, INSTANCE),
                ).rowcount
                if changed != 1:
                    raise RuntimeError("Owned run changed before completion")
        finally:
            self.current = None
            self._release()
