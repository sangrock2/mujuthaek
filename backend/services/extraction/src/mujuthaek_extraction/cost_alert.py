"""분야별 유료 AI 비용 집계와 월 상한 80% 슬랙 경고 (요구 2-10, 2026-10-23, migrations/V202610231000__extraction_spend_field_alerts.sql).

집계: 비용 장부(extraction_spend)의 유료 호출 수·비용을 분야(수집 이벤트 field: HOUSING·BUSINESS_SPACE·STARTUP_SUPPORT·SPACE_RECRUITMENT)별로
  한국 시간 달 단위로 셉니다. 응답을 못 받은 호출은 최악 비용으로 셉니다(상한 계산과 같음). 분야 칸이 생기기 전 줄은 작업 기록의 분야로,
  그것도 없으면 UNKNOWN. 로컬 AI 호출은 비용이 없어 장부에 없습니다. 검수 API GET /costs로도 봅니다.
경고: 이번 달 합계가 월 상한(EXTRACTION_MONTHLY_BUDGET_USD)의 80%를 넘으면 슬랙 수신 웹훅(EXTRACTION_SLACK_WEBHOOK_URL,
  없으면 공통 SLACK_WEBHOOK_URL)으로 한 번 보냅니다. 전송은 팀 공통 mujuthaek_platform.slack.SlackNotifier가 합니다(2026-10-23 공통으로 옮김).
  보냈다는 기록을 DB(extraction_alerts, 종류·달)에 두어 워커를 다시 시작하거나 워커가 여럿이어도 달마다 한 번만 보냅니다.
  보내기에 실패하면 기록을 되돌려 다음 처리 때 다시 보냅니다. 주소가 없으면 보내지 않고 경고 로그만 한 번 남깁니다.
  경고 확인·전송 실패는 추출을 막지 않습니다(로그만). 웹훅 주소는 로그에 남기지 않습니다.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import Any

from mujuthaek_platform.slack import DEFAULT_TIMEOUT_SECONDS, SlackNotifier

log = logging.getLogger(__name__)
ALERT_RATIO = 0.8
ALERT_KIND = "monthly_budget_80"
SLACK_TIMEOUT_SECONDS = DEFAULT_TIMEOUT_SECONDS

# 달 경계는 한국 시간(model/spend.py와 같음). month는 'YYYY-MM', 없으면 이번 달
_MONTH = "coalesce(to_date(%(month)s, 'YYYY-MM'), date_trunc('month', now() at time zone 'Asia/Seoul')::date)"
_IN_MONTH = f"s.created_at >= ({_MONTH})::timestamp at time zone 'Asia/Seoul' and s.created_at < (({_MONTH}) + interval '1 month') at time zone 'Asia/Seoul'"
_BY_FIELD_SQL = (
    "select coalesce(s.field, j.field, 'UNKNOWN') as field, count(*), coalesce(sum(coalesce(s.cost_usd, s.reserved_usd)), 0)"
    f" from extraction_spend s left join extraction_jobs j on j.id = s.job_id where {_IN_MONTH} group by 1 order by 1"
)
_PERIOD_SQL = f"select to_char({_MONTH}, 'YYYY-MM')"


def monthly_costs(conn, month: str | None = None, budget_usd: float | None = None) -> dict[str, Any]:
    """그 달(한국 시간, 'YYYY-MM', 없으면 이번 달)의 분야별 유료 호출 수·비용과 합계. budget_usd가 있으면 상한 대비 비율도."""
    period = conn.execute(_PERIOD_SQL, {"month": month}).fetchone()[0]
    rows = conn.execute(_BY_FIELD_SQL, {"month": month}).fetchall()
    fields = [{"field": field, "paidCalls": int(calls), "costUsd": round(float(cost), 4)} for field, calls, cost in rows]
    total = round(sum(float(cost) for _, _, cost in rows), 4)
    result: dict[str, Any] = {"month": period, "paidCalls": sum(f["paidCalls"] for f in fields), "costUsd": total, "fields": fields}
    if budget_usd:
        result |= {"budgetUsd": budget_usd, "budgetRatio": round(total / budget_usd, 4)}
    return result


def slack_sender(url: str, timeout: float = SLACK_TIMEOUT_SECONDS) -> Callable[[str], None]:
    """슬랙 수신 웹훅으로 글 하나를 보내는 함수(공통 SlackNotifier.send). 실패하면 SlackError(주소는 문구에 넣지 않음)."""
    return SlackNotifier(url, timeout=timeout).send


def alert_text(costs: dict[str, Any]) -> str:
    lines = [
        f"[extraction] {costs['month']} 유료 AI 비용이 월 상한의 {costs['budgetRatio']:.0%}입니다"
        f" (${costs['costUsd']:.2f} / ${costs['budgetUsd']:.2f}). 상한에 닿으면 새 추출을 미룹니다.",
        *(f"- {f['field']}: {f['paidCalls']}회, ${f['costUsd']:.2f}" for f in costs["fields"]),
    ]
    return "\n".join(lines)


class CostAlert:
    """월 비용이 상한의 80%를 넘으면 달마다 한 번 슬랙으로 알립니다. 워커 프로세스에 하나를 두고 처리마다 check를 부릅니다."""

    def __init__(self, monthly_usd: float, send: Callable[[str], None] | None, ratio: float = ALERT_RATIO):
        self.monthly_usd = monthly_usd
        self.send = send
        self.ratio = ratio
        self._warned_no_url = False
        self._lock = threading.Lock()

    @classmethod
    def from_url(cls, monthly_usd: float, url: str | None) -> CostAlert:
        return cls(monthly_usd, slack_sender(url) if url else None)

    def check(self, conn) -> bool:
        """이번 달 합계가 기준을 넘었고 아직 알리지 않았으면 보내고 True. 오류는 로그만 남기고 False(추출을 막지 않음)."""
        try:
            return self._check(conn)
        except Exception:
            log.exception("월 비용 경고를 확인하지 못했습니다")
            return False

    def _check(self, conn) -> bool:
        if self.monthly_usd <= 0:
            return False
        costs = monthly_costs(conn, budget_usd=self.monthly_usd)
        if costs["costUsd"] < self.monthly_usd * self.ratio:
            return False
        if self.send is None:
            with self._lock:
                if not self._warned_no_url:
                    self._warned_no_url = True
                    log.warning(
                        "월 비용이 상한의 80%를 넘었지만 슬랙 주소(EXTRACTION_SLACK_WEBHOOK_URL 또는 SLACK_WEBHOOK_URL)가 없어 알리지 않았습니다",
                        extra={"month": costs["month"], "costUsd": costs["costUsd"], "budgetUsd": self.monthly_usd},
                    )
            return False
        with conn.transaction():
            claimed = conn.execute(
                "insert into extraction_alerts (kind, period) values (%s, %s) on conflict do nothing returning kind", (ALERT_KIND, costs["month"])
            ).fetchone()
            if claimed is None:  # 이번 달은 이미 보냄(다른 워커·재시작 전)
                return False
            self.send(alert_text(costs))  # 실패하면 예외로 트랜잭션이 되돌아가 다음에 다시 보냅니다
        log.warning("월 비용 80% 경고를 슬랙으로 보냈습니다", extra={"month": costs["month"], "costUsd": costs["costUsd"], "budgetUsd": self.monthly_usd})
        return True
