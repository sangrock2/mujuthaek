"""유료 모델 비용 장부와 하루·월 전체 상한 (2026-10-21, migrations/V202610211300__extraction_spend.sql).

공고당 상한(Budget)만 있으면 공고 수·버전 수만큼 비용이 열려 있습니다. 장부는 모든 처리·워커가 같이 쓰는 DB 표라서,
여러 처리가 동시에 돌아도 하루·월 합계로 막을 수 있습니다.

- 호출 전: 최악 비용을 적고(reserve), 합계가 상한을 넘으면 적지 않고 거절합니다. 확인과 기록을 DB 잠금 안에서 해 동시 처리가 함께 넘지 않습니다.
- 응답 뒤: 실제 비용으로 바꿉니다(settle). 청구되지 않은 실패면 지웁니다(release).
- 프로세스가 죽으면 최악 비용이 그대로 남아 합계에 들어갑니다(청구됐을 수 있으므로 넉넉히 셈).
- 분야(field)도 적어 분야별 비용을 셉니다. 비용을 적은 처리가 끝나면(close) 월 상한 80% 경고를 확인합니다(cost_alert.py, 2026-10-23).
연결은 장부 전용입니다(모델 호출 스레드에서 트랜잭션을 쓰므로 작업 저장 연결과 나눕니다).
"""

from __future__ import annotations

import threading
import uuid
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mujuthaek_extraction.cost_alert import CostAlert

# 날·달 경계는 한국 시간으로 셉니다
_DAY_START = "date_trunc('day', now() at time zone 'Asia/Seoul') at time zone 'Asia/Seoul'"
_MONTH_START = "date_trunc('month', now() at time zone 'Asia/Seoul') at time zone 'Asia/Seoul'"
_PERIOD_SQL = (
    f"select coalesce(sum(coalesce(cost_usd, reserved_usd)) filter (where created_at >= {_DAY_START}), 0),"
    f" coalesce(sum(coalesce(cost_usd, reserved_usd)), 0) from extraction_spend where created_at >= {_MONTH_START}"
)
_LOCK_KEY = "extraction_spend"


class SpendLedger:
    """한 처리(run)의 비용을 DB 장부에 적고 하루·월 상한을 지킵니다."""

    def __init__(self, conn, *, daily_usd: float, monthly_usd: float, scope: dict[str, Any] | None = None, alert: CostAlert | None = None):
        conn.autocommit = True
        self.conn = conn
        self.daily_usd = daily_usd
        self.monthly_usd = monthly_usd
        self.run_id = str(uuid.uuid4())
        scope = scope or {}
        self._scope = (scope.get("eventId"), scope.get("rawPostId"), scope.get("rawVersion"), scope.get("field"))
        self.alert = alert  # 월 상한 80% 경고(cost_alert.py). 이 처리가 비용을 적었으면 닫을 때 확인합니다
        self._charged = False
        self._lock = threading.Lock()
        self.refused: str | None = None  # 거절한 이유(하루·월). 처리 결과를 다시 처리 대상으로 바꿀 때 씁니다

    def totals(self) -> tuple[float, float]:
        """(오늘 합계, 이번 달 합계) USD. 응답을 못 받은 호출은 최악 비용으로 셉니다."""
        with self._lock:
            row = self.conn.execute(_PERIOD_SQL).fetchone()
        return float(row[0]), float(row[1])

    def room(self, worst_usd: float) -> str | None:
        """worst_usd를 더 써도 상한 안이면 None, 넘으면 이유."""
        day, month = self.totals()
        return self._reason(day, month, worst_usd)

    def _reason(self, day: float, month: float, worst: float) -> str | None:
        if day + worst > self.daily_usd:
            return f"하루 비용 상한(${self.daily_usd:.2f})"
        if month + worst > self.monthly_usd:
            return f"월 비용 상한(${self.monthly_usd:.2f})"
        return None

    def reserve(self, model: str, worst_usd: float) -> str | None:
        """상한 안이면 최악 비용을 적고 장부 ID를, 넘으면 None을 돌려줍니다."""
        with self._lock, self.conn.transaction():
            self.conn.execute("select pg_advisory_xact_lock(hashtext(%s))", (_LOCK_KEY,))
            day, month = self.conn.execute(_PERIOD_SQL).fetchone()
            reason = self._reason(float(day), float(month), worst_usd)
            if reason:
                self.refused = reason
                return None
            entry = str(uuid.uuid4())
            self.conn.execute(
                "insert into extraction_spend (id, run_id, event_id, raw_post_id, raw_version, field, model, reserved_usd)"
                " values (%s, %s, %s, %s, %s, %s, %s, %s)",
                (entry, self.run_id, *self._scope, model, round(worst_usd, 6)),
            )
            self._charged = True
            return entry

    def settle(self, entry: str, cost_usd: float) -> None:
        with self._lock:
            self.conn.execute("update extraction_spend set cost_usd = %s, settled_at = now() where id = %s", (round(cost_usd, 6), entry))

    def release(self, entry: str) -> None:
        with self._lock:
            self.conn.execute("delete from extraction_spend where id = %s", (entry,))

    def close(self) -> None:
        try:
            if self.alert is not None and self._charged:
                self.alert.check(self.conn)  # 오류는 check 안에서 로그만 남깁니다
        finally:
            self.conn.close()
