"""검수 API (:8092). 사람이 확인할 공고를 조회하고 승인·반려합니다.

  GET  /health                       상태 (워커의 큐 소비·발행·다시 처리 중 하나라도 신호가 끊기면 503)
  GET  /reviews?status=PENDING       검수 목록 (PENDING·APPROVED·REJECTED·SUPERSEDED). 기본 PENDING에는 대체된 건이 없습니다
                                     &reason=MUST·CHECK·FORMAT로 거르고 &afterAt=&afterId=(앞 페이지 마지막 건)부터 이어 받아요(hasMore)
                                     SUPERSEDED: 같은 공고의 새 버전(또는 정정공고)이 발행되어 대체된 건, supersededBy에 대체한 작업·공고·버전
  GET  /reviews/{jobId}              검수 상세 (표준 공고 후보·이슈·받은 이벤트)
  GET  /reviews/{jobId}/trace        추출 과정 (관리자 「추출 과정 보기」, trace_view.py): 담당별 도구 호출·거절·검증 메시지·초안 요약과 호출별 토큰·비용.
                                     검수 대기에 오르지 않은 작업도 작업 ID로 볼 수 있어요. 근거 id → 원문 PDF 쪽 대응표(documents·refs)도 함께 줘요
  GET  /reviews/{jobId}/files        작업 원본의 첨부 위치(문서 ID·이름·형식·s3Key·해시). api가 관리자 원문 PDF 보기에서 S3를 읽을 때 씁니다
  POST /reviews/{jobId}/approve      승인 → extraction.completed(reviewStatus APPROVED) 다시 발행
                                     본문(선택): {"candidate": 고친 표준 공고 | "edits": [{"path": "/eligibility/3/description", "value": …}],
                                                 "note": "메모", "reviewer": "검수자"}
                                     edits는 칸별 수정(관리자 화면, 2026-10-25): 있는 칸만 바꾸고(새 칸 추가 없음) 원본·버전·검증 기록 칸은 못 바꿉니다
  POST /reviews/{jobId}/reject       반려 (발행 없음). 본문(선택): {"note": "메모", "reviewer": "검수자"}
  POST /reviews/reopen               이미 발행한 결과를 검수 대기로 다시 열기 {"rawPostId": "…", "reviewer": "…", "note": "공고 제보"}
                                     (그 원본의 가장 새로 발행한 작업. 앞선 처리 기록은 상세의 history로)
  GET  /reviews/activity?days=30&limit=300  처리 기록(관리자 「처리 기록」): 공고·혜택 검수 승인·고쳐서 승인·반려·다시 열기를 최근 순으로
                                     (kind NOTICE·BENEFIT, action APPROVED·EDITED_APPROVED·REJECTED·REOPENED, by 처리한 관리자, note)
  GET  /reviews/stats?days=7         처리 통계(최근 days일·오늘): 그대로 승인·고쳐서 승인·반려 수, 처리까지 걸린 시간 중앙값(분)
  GET  /costs?month=2026-10          분야별 유료 AI 호출 수·비용과 월 상한 대비 비율(한국 시간 달, month 없으면 이번 달, cost_alert.py)
  GET  /stats/extraction?days=30     관리자 「추출 비용·품질」(extraction_stats.py): 최근 days일(1~90, 한국 시간)의 처리 공고 수, 상태 묶음별 비율
                                     (검수 없이 게시 비율), 공고당 평균·최대 비용, 담당별 비용 비중, 캐시 읽기 비율, 멈춤·넣기 거절·해결 담당 채택,
                                     하루 추이, 비용이 큰 작업

혜택(주거·이주 정책) 검수 (2026-10-25): 확인 필요(needsReview) 정제 결과와 정책 제보로 다시 연 결과. 결과는 이미 발행돼 있고
(policy.extracted, quality.needsReview=true), 처리하면 고친 결과를 reprocess=true(알림 없음)로 다시 발행합니다.
  GET  /benefit-reviews?status=PENDING          목록 (PENDING·APPROVED·REJECTED·SUPERSEDED) · &reported=true·false · &afterAt=&afterId= 이어 받기(hasMore)
  GET  /benefit-reviews/{reviewId}              상세 (payload: 정제 결과, source: 받은 원본 payload)
  POST /benefit-reviews/{reviewId}/approve      승인 → 확인 필요를 풀어 다시 발행. 본문(선택): {"edits": [{"path": "/conditions/0/value", "value": …}],
                                                "note": "메모", "reviewer": "검수자"}. 원본·버전·출처·품질 칸은 못 바꿉니다
  POST /benefit-reviews/{reviewId}/reject       반려 → relevant=false(서비스에 안 보임)로 다시 발행. 본문(선택): {"note", "reviewer"}
  POST /benefit-reviews/reopen                  정책 제보로 그 정책의 가장 새 결과를 검수 대기로 다시 열기 {"rawPolicyId", "reviewer", "note"}
  GET  /benefits/{rawPolicyId}                  그 정책의 가장 새 결과 요약(제보 받을 정책이 있는지 볼 때)

인증(검토 2026-10-16): EXTRACTION_REVIEW_TOKEN이 있으면 /health 밖의 모든 요청에 'Authorization: Bearer <토큰>'이 필요합니다.
토큰이 없으면 같은 컴퓨터(127.0.0.1·::1)에서 온 요청만 받습니다 — Docker처럼 0.0.0.0에 열어도 밖에서는 못 씁니다.
승인할 후보는 그 작업의 원본·버전·분야와 같아야 합니다(다른 공고의 결과를 발행하지 못하게).
대체된(SUPERSEDED) 건은 승인·반려하면 409와 함께 대체한 버전을 알려 줍니다(store.py 검수 대기 건 대체).
"""

from __future__ import annotations

import copy
import hmac
import json
import logging
import re
import uuid
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from mujuthaek_extraction.assemble.details import upgrade_stored
from mujuthaek_extraction.contracts import tools
from mujuthaek_extraction.extraction_stats import MAX_DAYS as MAX_STATS_DAYS
from mujuthaek_extraction.publish import approved_payload, source_files
from mujuthaek_extraction.store import REVIEW_REASON_SQL, SUPERSEDED, superseded_message
from mujuthaek_extraction.trace_view import trace_view

log = logging.getLogger(__name__)
CANDIDATE_SCHEMA = "schemas/extracted-notice.v1.json"
EVENT_SCHEMA = "events/extraction.completed.v1.json"
REVIEW_PATH = re.compile(r"^/reviews/([0-9a-fA-F-]{36})(?:/(approve|reject))?$")
TRACE_PATH = re.compile(r"^/reviews/([0-9a-fA-F-]{36})/trace$")
FILES_PATH = re.compile(r"^/reviews/([0-9a-fA-F-]{36})/files$")
BENEFIT_REVIEW_PATH = re.compile(r"^/benefit-reviews/([0-9a-fA-F-]{36})(?:/(approve|reject))?$")
BENEFIT_PATH = re.compile(r"^/benefits/([0-9a-fA-F-]{36})$")
BENEFIT_EVENT_SCHEMA = "events/policy.extracted.v1.json"
# 혜택 칸별 수정으로 바꾸지 못하는 칸: 어느 정책·버전인지와 출처 기본 칸, 품질 기록(검수 결과는 코드가 정함)
BENEFIT_LOCKED_ROOTS = frozenset({"rawPolicyId", "version", "sourceCode", "provider", "policyId", "field", "reprocess", "source", "quality"})
MAX_BODY = 5 * 1024 * 1024
LOOPBACK = {"127.0.0.1", "::1", "::ffff:127.0.0.1"}
MONTH = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
REVIEW_LIST_STATUSES = ("PENDING", "APPROVED", "REJECTED", SUPERSEDED)
MAX_EDITS = 200
# 칸별 수정으로 바꾸지 못하는 칸: 어느 공고·버전인지와 자동 검증 기록·근거 원문(바꾸면 다른 공고 결과를 발행하거나 근거가 흔들림)
LOCKED_ROOTS = frozenset({"schemaVersion", "target", "input", "sourceReferences", "documents", "evidence", "quality"})


def _pointer_tokens(path: str) -> list[str] | None:
    """JSON Pointer(RFC 6901)를 낱말로. 형식이 틀리면 None."""
    if not path.startswith("/") or path == "/":
        return None
    return [token.replace("~1", "/").replace("~0", "~") for token in path[1:].split("/")]


def apply_edits(candidate: dict[str, Any], edits: Any, locked: frozenset[str] = LOCKED_ROOTS) -> tuple[list[dict[str, Any]] | None, str | None]:
    """칸별 수정을 후보에 적용합니다(candidate를 바꿈). 있는 칸의 값만 바꾸고, 바꾼 기록 [{path, before, after}]을 돌려줍니다.
    locked는 고칠 수 없는 맨 위 칸(공고 후보 기본, 혜택은 BENEFIT_LOCKED_ROOTS). 잘못된 수정이면 (None, 이유)."""
    if not isinstance(edits, list) or not edits:
        return None, "edits는 한 개 이상의 수정 목록이어야 합니다."
    if len(edits) > MAX_EDITS:
        return None, f"한 번에 {MAX_EDITS}개까지 고칠 수 있습니다."
    applied = []
    for edit in edits:
        if not isinstance(edit, dict) or not isinstance(edit.get("path"), str) or "value" not in edit:
            return None, "각 수정은 {path, value} 모양이어야 합니다."
        tokens = _pointer_tokens(edit["path"])
        if tokens is None:
            return None, f"{edit['path']!r}는 JSON Pointer가 아닙니다."
        if tokens[0] in locked:
            return None, f"{edit['path']}는 고칠 수 없는 칸입니다(원본·버전·검증 기록)."
        parent: Any = candidate
        for token in tokens[:-1]:
            parent = _child(parent, token)
            if parent is None:
                return None, f"{edit['path']}에 해당하는 칸이 없습니다."
        last = tokens[-1]
        if isinstance(parent, dict) and last in parent:
            before = parent[last]
            parent[last] = edit["value"]
        elif isinstance(parent, list) and last.isdigit() and int(last) < len(parent):
            before = parent[int(last)]
            parent[int(last)] = edit["value"]
        else:
            return None, f"{edit['path']}에 해당하는 칸이 없습니다(새 칸은 추가하지 않습니다)."
        applied.append({"path": edit["path"], "before": before, "after": edit["value"]})
    return applied, None


def _child(node: Any, token: str) -> Any:
    if isinstance(node, dict):
        return node.get(token)
    if isinstance(node, list) and token.isdigit() and int(token) < len(node):
        return node[int(token)]
    return None


def _same_notice(candidate: dict[str, Any], raw_payload: dict[str, Any]) -> bool:
    """후보의 원본·버전·분야가 작업이 받은 이벤트와 같은지. 출처 기록(sourceReferences)도 같은 원본을 가리켜야 합니다."""
    given = candidate.get("input") or {}
    expected = (str(raw_payload.get("rawPostId")), raw_payload.get("version"), raw_payload.get("field"))
    if (str(given.get("rawPostId")), given.get("rawVersion"), given.get("field")) != expected:
        return False
    references = candidate.get("sourceReferences") or []
    return all((str(r.get("rawPostId")), r.get("rawVersion")) == expected[:2] for r in references)


MAX_LIST_LIMIT = 1000
REJECTED_RELEVANCE_REASON = "관리자가 확인해 서비스 대상에서 뺐어요"


def _list_limit(raw: str | None) -> int | None:
    """목록 limit 칸: 비우면 최대값, 1~MAX_LIST_LIMIT 정수가 아니면 None(400)."""
    if raw is None or raw == "":
        return MAX_LIST_LIMIT
    return int(raw) if raw.isdigit() and 1 <= int(raw) <= MAX_LIST_LIMIT else None


def _list_after(at: str | None, item_id: str | None) -> tuple[str, str] | None | str:
    """이어 받기 칸(afterAt 들어온 시각, afterId 그 건 ID): 둘 다 없으면 처음부터(None), 둘 중 하나만 있거나 형식이 틀리면 오류 글."""
    if at is None and item_id is None:
        return None
    if at is None or item_id is None:
        return "afterAt과 afterId는 함께 보내야 합니다."
    try:
        return datetime.fromisoformat(at).isoformat(), str(uuid.UUID(item_id))
    except ValueError:
        return "afterAt은 ISO 시각, afterId는 UUID여야 합니다."


def _page(items: list[dict[str, Any]], size: int) -> tuple[list[dict[str, Any]], bool]:
    """size+1건을 받아 size건과 더 있는지를 나눠요."""
    return items[:size], len(items) > size


class ReviewService:
    """HTTP와 분리한 검수 동작. store_session은 JobStore를 여는 컨텍스트입니다(실행 중에는 연결 풀에서 빌려요)."""

    def __init__(
        self,
        store_session: Callable[[], AbstractContextManager[Any]],
        new_event: Callable[[str, str, dict[str, Any]], dict[str, Any]],
        monthly_budget_usd: float | None = None,
    ):
        self.store_session = store_session
        self.new_event = new_event
        self.monthly_budget_usd = monthly_budget_usd  # 비용 집계에 상한 대비 비율을 붙일 때 씁니다

    def costs(self, month: str | None) -> tuple[int, Any]:
        """그 달의 분야별 유료 AI 호출 수·비용. month는 'YYYY-MM'."""
        if month is not None and not MONTH.match(month):
            return 400, {"error": "month는 YYYY-MM 형식입니다."}
        with self.store_session() as store:
            return 200, store.monthly_costs(month, self.monthly_budget_usd)

    def extraction_stats(self, days: str | None) -> tuple[int, Any]:
        """추출 비용·품질 집계. days는 1~90(기본 30)."""
        try:
            value = 30 if days is None else int(days)
        except ValueError:
            value = 0
        if not 1 <= value <= MAX_STATS_DAYS:
            return 400, {"error": f"days는 1~{MAX_STATS_DAYS} 사이 정수입니다."}
        with self.store_session() as store:
            return 200, store.extraction_stats(value)

    def activity(self, days: str | None, limit: str | None) -> tuple[int, Any]:
        """처리 기록. days는 1~90(기본 30), limit은 1~1000(기본 300)."""
        try:
            value = 30 if days is None else int(days)
        except ValueError:
            value = 0
        if not 1 <= value <= 90:
            return 400, {"error": "days는 1~90 사이 정수입니다."}
        size = 300 if limit is None else _list_limit(limit)
        if size is None:
            return 400, {"error": f"limit은 1~{MAX_LIST_LIMIT} 사이 정수입니다."}
        with self.store_session() as store:
            return 200, {"items": store.review_activity(value, size)}

    def stats(self, days: str | None) -> tuple[int, Any]:
        """처리 통계. days는 1~90(기본 7)."""
        try:
            value = 7 if days is None else int(days)
        except ValueError:
            value = 0
        if not 1 <= value <= 90:
            return 400, {"error": "days는 1~90 사이 정수입니다."}
        with self.store_session() as store:
            return 200, store.review_stats(value)

    def reopen(self, body: dict[str, Any]) -> tuple[int, Any]:
        """이미 발행한 결과를 검수 대기로 다시 엽니다(사용자 제보로 공고 값을 고칠 때)."""
        try:
            raw_post_id = str(uuid.UUID(str(body.get("rawPostId"))))
        except ValueError:
            return 400, {"error": "rawPostId는 UUID여야 합니다."}
        with self.store_session() as store:
            opened = store.reopen(raw_post_id, body.get("reviewer"), body.get("note"))
        if opened is None:
            return 404, {"error": "그 원본으로 발행한 결과가 없습니다."}
        log.info("검수 다시 열기", extra={"jobId": opened["jobId"], "reopened": opened["reopened"]})
        return 200, opened

    def list(
        self,
        status: str,
        limit: str | None = None,
        reason: str | None = None,
        after_at: str | None = None,
        after_id: str | None = None,
    ) -> tuple[int, Any]:
        """검수 목록(오래된 것부터 limit건, 기본·최대 1000)과 그 조건의 전체 건수 total. 건수는 목록 길이가 아니라 total을 쓰세요(2026-10-25 검토).
        reason(MUST·CHECK·FORMAT)으로 거르고, afterAt·afterId(앞 페이지 마지막 건)부터 이어 받아요. hasMore면 다음 페이지가 있어요."""
        if status not in REVIEW_LIST_STATUSES:
            return 400, {"error": "status는 " + "·".join(REVIEW_LIST_STATUSES) + " 중 하나입니다."}
        size = _list_limit(limit)
        if size is None:
            return 400, {"error": f"limit은 1~{MAX_LIST_LIMIT} 사이 정수입니다."}
        if reason is not None and reason not in REVIEW_REASON_SQL:
            return 400, {"error": "reason은 " + "·".join(REVIEW_REASON_SQL) + " 중 하나입니다."}
        after = _list_after(after_at, after_id)
        if isinstance(after, str):
            return 400, {"error": after}
        with self.store_session() as store:
            items, more = _page(store.reviews(status, size + 1, reason, after), size)
            return 200, {"items": items, "total": store.review_count(status, reason), "hasMore": more}

    def detail(self, job_id: str) -> tuple[int, Any]:
        with self.store_session() as store:
            item = store.review(job_id)
        return (200, item) if item else (404, {"error": "검수 항목이 없습니다."})

    def trace(self, job_id: str) -> tuple[int, Any]:
        """작업 하나의 추출 과정(trace_view). 측정 기록이 없는 작업(처리 전·아주 예전 작업)은 빈 요약입니다."""
        with self.store_session() as store:
            job = store.job_usage(job_id)
        if job is None:
            return 404, {"error": "작업이 없습니다."}
        usage, pdfs, text_led = job.pop("usage"), job.pop("pdfs", None), job.pop("textLed", False)
        return 200, {**job, **trace_view(usage if isinstance(usage, dict) else None, pdfs, text_led=text_led)}

    def files(self, job_id: str) -> tuple[int, Any]:
        """작업 원본의 첨부 위치(관리자 원문 PDF 보기, api가 S3에서 읽어 내려줌). 문서 ID는 추출 결과 documents[].id와 같아요."""
        with self.store_session() as store:
            files = store.job_files(job_id)
        if files is None:
            return 404, {"error": "작업이 없습니다."}
        return 200, {"files": files}

    def approve(self, job_id: str, body: dict[str, Any]) -> tuple[int, Any]:
        """검수 대기 작업을 승인하고 APPROVED 이벤트를 저장합니다. 고친 후보가 오면 그것을 쓰되 계약·같은 공고인지 먼저 확인합니다."""
        with self.store_session() as store:
            item = store.review(job_id)
            if item is None:
                return 404, {"error": "검수 항목이 없습니다."}
            if item["reviewStatus"] == SUPERSEDED and item.get("supersededBy"):
                by = item["supersededBy"]
                return 409, {"error": superseded_message(item.get("rawPostId"), by["rawPostId"], by["version"], by["jobId"]), "supersededBy": by}
            if item["reviewStatus"] != "PENDING":
                return 409, {"error": f"이미 {item['reviewStatus']} 처리된 항목입니다."}
            if body.get("candidate") is not None and body.get("edits") is not None:
                return 422, {"error": "고친 후보 전체(candidate)와 칸별 수정(edits)은 함께 보낼 수 없습니다."}
            candidate = body.get("candidate") or item["candidate"]
            if candidate is None:
                return 409, {"error": "추출 결과가 없어 승인할 수 없습니다. 원본 자료를 고친 뒤 다시 처리하세요."}
            # 2026-10-23 이전에 저장한 후보는 일정·서류의 새 칸과 정해진 신청 방법 값으로 옮긴 뒤 검사합니다(새 형식이면 그대로)
            candidate = upgrade_stored(copy.deepcopy(candidate))
            edits = None
            if body.get("edits") is not None:
                edits, problem = apply_edits(candidate, body["edits"])
                if problem:
                    return 422, {"error": problem}
            errors = tools().validate(candidate, CANDIDATE_SCHEMA)
            if errors:
                return 422, {"error": "표준 공고 형식이 맞지 않습니다.", "details": errors[:20]}
            raw = (item["rawEvent"] or {}).get("payload") or {}
            if not _same_notice(candidate, raw):
                return 422, {"error": "후보의 원본·버전·분야가 이 검수 작업의 공고와 다릅니다."}
            payload = approved_payload(candidate, provider=raw.get("provider"), files=source_files(raw, candidate))
            event = {**self.new_event("extraction.completed", "extraction", payload), "traceId": (item["rawEvent"] or {}).get("traceId")}
            errors = tools().validate(event, EVENT_SCHEMA)
            if errors:
                return 422, {"error": "발행할 이벤트가 계약과 맞지 않습니다.", "details": errors[:20]}
            try:
                store.approve(
                    job_id,
                    candidate,
                    event,
                    body.get("note"),
                    reviewer=body.get("reviewer"),
                    edited=edits is not None or body.get("candidate") is not None,
                    edits=edits,
                )
            except LookupError as error:
                return 409, {"error": str(error)}
        log.info("검수 승인", extra={"jobId": job_id, "eventId": event["eventId"]})
        return 200, {"jobId": job_id, "eventId": event["eventId"], "reviewStatus": "APPROVED"}

    def reject(self, job_id: str, body: dict[str, Any]) -> tuple[int, Any]:
        with self.store_session() as store:
            try:
                store.reject(job_id, body.get("note"), reviewer=body.get("reviewer"))
            except LookupError as error:
                return 409, {"error": str(error)}
        log.info("검수 반려", extra={"jobId": job_id})
        return 200, {"jobId": job_id, "reviewStatus": "REJECTED"}

    # ---- 혜택 검수 (2026-10-25) ----
    def benefit_list(
        self,
        status: str,
        limit: str | None = None,
        reported: str | None = None,
        after_at: str | None = None,
        after_id: str | None = None,
    ) -> tuple[int, Any]:
        """혜택 검수 목록(오래된 것부터 limit건, 기본·최대 1000)과 그 조건의 전체 건수 total.
        reported(true·false)로 정책 제보로 다시 연 건을 거르고, afterAt·afterId부터 이어 받아요. hasMore면 다음 페이지가 있어요."""
        if status not in REVIEW_LIST_STATUSES:
            return 400, {"error": "status는 " + "·".join(REVIEW_LIST_STATUSES) + " 중 하나입니다."}
        size = _list_limit(limit)
        if size is None:
            return 400, {"error": f"limit은 1~{MAX_LIST_LIMIT} 사이 정수입니다."}
        if reported not in (None, "true", "false"):
            return 400, {"error": "reported는 true·false 중 하나입니다."}
        after = _list_after(after_at, after_id)
        if isinstance(after, str):
            return 400, {"error": after}
        flag = None if reported is None else reported == "true"
        with self.store_session() as store:
            items, more = _page(store.benefit_reviews(status, size + 1, flag, after), size)
            return 200, {"items": items, "total": store.benefit_review_count(status, flag), "hasMore": more}

    def benefit_detail(self, review_id: str) -> tuple[int, Any]:
        with self.store_session() as store:
            item = store.benefit_review(review_id)
        return (200, item) if item else (404, {"error": "혜택 검수 항목이 없습니다."})

    def benefit_summary(self, raw_policy_id: str) -> tuple[int, Any]:
        with self.store_session() as store:
            item = store.benefit(raw_policy_id)
        return (200, item) if item else (404, {"error": "그 정책의 정제 결과가 없습니다."})

    def benefit_reopen(self, body: dict[str, Any]) -> tuple[int, Any]:
        try:
            raw_policy_id = str(uuid.UUID(str(body.get("rawPolicyId"))))
        except ValueError:
            return 400, {"error": "rawPolicyId는 UUID여야 합니다."}
        with self.store_session() as store:
            opened = store.reopen_benefit(raw_policy_id, body.get("reviewer"), body.get("note"))
        if opened is None:
            return 404, {"error": "그 정책의 정제 결과가 없습니다."}
        log.info("혜택 검수 다시 열기", extra={"reviewId": opened["reviewId"], "reopened": opened["reopened"]})
        return 200, opened

    def benefit_decide(self, review_id: str, decision: str, body: dict[str, Any]) -> tuple[int, Any]:
        """승인(APPROVED): 칸별 수정을 적용하고 확인 필요를 풀어 다시 발행. 반려(REJECTED): relevant=false로 다시 발행(서비스에 안 보임).
        둘 다 reprocess=true라 사용자 알림을 보내지 않습니다."""
        with self.store_session() as store:
            item = store.benefit_review(review_id)
            if item is None:
                return 404, {"error": "혜택 검수 항목이 없습니다."}
            if item["reviewStatus"] != "PENDING":
                return 409, {"error": f"이미 {item['reviewStatus']} 처리된 항목입니다."}
            payload = copy.deepcopy(item["payload"])
            edits = None
            if decision == "APPROVED" and body.get("edits") is not None:
                edits, problem = apply_edits(payload, body["edits"], BENEFIT_LOCKED_ROOTS)
                if problem:
                    return 422, {"error": problem}
            if decision == "REJECTED":
                # 반려 메모는 내부 기록(benefit_reviews.note)에만 남기고, 발행 값에는 고정 문구만 넣어요.
                # 메모가 회원 화면까지 나갈 수 있었음(2026-10-25 검토)
                payload["relevant"] = False
                payload["relevanceReason"] = REJECTED_RELEVANCE_REASON
            payload["reprocess"] = True
            quality = payload["quality"]
            quality["needsReview"] = False
            # 검수 전 결과가 같은 버전으로 이미 나가 있어, 표시가 없으면 api가 같은 버전이라 버렸습니다(2026-11-10 코드 검토)
            quality["reviewed"] = True
            quality["reviewReasons"] = [r for r in quality.get("reviewReasons", []) if r == "NO_DOCUMENT"]  # 사람이 확인함
            event = self.new_event("policy.extracted", "extraction", payload)
            errors = tools().validate(event, BENEFIT_EVENT_SCHEMA)
            if errors:
                return 422, {"error": "발행할 이벤트가 계약과 맞지 않습니다.", "details": errors[:20]}
            try:
                store.decide_benefit(review_id, decision, event, body.get("note"), body.get("reviewer"), edits)
            except LookupError as error:
                return 409, {"error": str(error)}
        log.info("혜택 검수 처리", extra={"reviewId": review_id, "decision": decision, "eventId": event["eventId"]})
        return 200, {"reviewId": review_id, "eventId": event["eventId"], "reviewStatus": decision}


def handler_for(service: ReviewService, token: str | None = None, health: Any = None) -> type[BaseHTTPRequestHandler]:
    """검수 서비스·토큰·생존 신호를 묶은 HTTP 요청 처리 클래스를 만들어 돌려줍니다."""

    class Handler(BaseHTTPRequestHandler):
        """검수 API 주소를 ReviewService 동작에 연결하고, 인증과 JSON 응답을 맡습니다."""

        def _allowed(self) -> bool:
            if token:
                given = self.headers.get("Authorization") or ""
                return hmac.compare_digest(given.encode(), f"Bearer {token}".encode())
            return self.client_address[0] in LOOPBACK

        def _send(self, status: int, body: Any) -> None:
            data = json.dumps(body, ensure_ascii=False, default=str).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _body(self) -> dict[str, Any] | None:
            """요청 본문을 JSON 객체로 읽습니다. 본문이 없으면 빈 객체, 길이·형식이 맞지 않거나 note가 글자가 아니면 None입니다.
            조각 전송(Transfer-Encoding: chunked)도 읽습니다(2026-10-25: api 서버가 길이 없이 보내 본문이 빈 것으로 읽혀 승인·반려가 400이 됨)."""
            if "chunked" in (self.headers.get("Transfer-Encoding") or "").lower():
                raw = self._chunked()
                if raw is None:
                    return None
            else:
                try:
                    length = int(self.headers.get("Content-Length") or 0)
                except ValueError:
                    return None
                if length == 0:
                    return {}
                if not 0 < length <= MAX_BODY:  # 음수 길이는 끝까지 읽어 버리므로 거절합니다
                    return None
                raw = self.rfile.read(length)
            if not raw.strip():
                return {}
            try:
                value = json.loads(raw)
            except ValueError:
                return None
            if not isinstance(value, dict) or not isinstance(value.get("note"), str | None) or not isinstance(value.get("reviewer"), str | None):
                return None
            return value

        def _chunked(self) -> bytes | None:
            """조각 전송 본문을 이어 붙입니다. MAX_BODY를 넘거나 형식이 틀리면 None."""
            data = b""
            while True:
                line = self.rfile.readline(64).strip()
                try:
                    size = int(line.split(b";")[0], 16)
                except ValueError:
                    return None
                if size == 0:
                    while self.rfile.readline(1024).strip():  # 끝 머리말(trailer)은 버림
                        pass
                    return data
                if len(data) + size > MAX_BODY:
                    return None
                data += self.rfile.read(size)
                self.rfile.readline(4)  # 조각 끝 CRLF

        def _job_id(self, match: re.Match[str]) -> str | None:
            try:
                return str(uuid.UUID(match[1]))
            except ValueError:
                return None

        def do_GET(self) -> None:  # noqa: N802
            """/health는 인증 없이, 검수 목록·상세는 인증을 확인한 뒤 응답합니다."""
            url = urlparse(self.path)
            if url.path == "/health":
                if health is None:
                    return self._send(200, {"status": "ok"})
                ok, parts = health.report()
                return self._send(200 if ok else 503, {"status": "ok" if ok else "degraded", "parts": parts})
            if not self._allowed():
                return self._send(401, {"error": "인증이 필요합니다."})
            if url.path == "/reviews":
                query = {k: v[0] for k, v in parse_qs(url.query).items()}
                return self._send(
                    *service.list(query.get("status", "PENDING"), query.get("limit"), query.get("reason"), query.get("afterAt"), query.get("afterId"))
                )
            if url.path == "/reviews/activity":
                query = parse_qs(url.query)
                return self._send(*service.activity(query.get("days", [None])[0], query.get("limit", [None])[0]))
            if url.path == "/reviews/stats":
                return self._send(*service.stats(parse_qs(url.query).get("days", [None])[0]))
            if url.path == "/stats/extraction":
                return self._send(*service.extraction_stats(parse_qs(url.query).get("days", [None])[0]))
            if url.path == "/costs":
                return self._send(*service.costs(parse_qs(url.query).get("month", [None])[0]))
            if url.path == "/benefit-reviews":
                query = {k: v[0] for k, v in parse_qs(url.query).items()}
                return self._send(
                    *service.benefit_list(query.get("status", "PENDING"), query.get("limit"), query.get("reported"), query.get("afterAt"), query.get("afterId"))
                )
            match = REVIEW_PATH.match(url.path)
            if match and not match[2]:
                job_id = self._job_id(match)
                return self._send(*service.detail(job_id)) if job_id else self._send(400, {"error": "작업 ID 형식이 아닙니다."})
            match = TRACE_PATH.match(url.path)
            if match:
                job_id = self._job_id(match)
                return self._send(*service.trace(job_id)) if job_id else self._send(400, {"error": "작업 ID 형식이 아닙니다."})
            match = FILES_PATH.match(url.path)
            if match:
                job_id = self._job_id(match)
                return self._send(*service.files(job_id)) if job_id else self._send(400, {"error": "작업 ID 형식이 아닙니다."})
            match = BENEFIT_REVIEW_PATH.match(url.path)
            if match and not match[2]:
                review_id = self._job_id(match)
                return self._send(*service.benefit_detail(review_id)) if review_id else self._send(400, {"error": "검수 ID 형식이 아닙니다."})
            match = BENEFIT_PATH.match(url.path)
            if match:
                policy_id = self._job_id(match)
                return self._send(*service.benefit_summary(policy_id)) if policy_id else self._send(400, {"error": "정책 ID 형식이 아닙니다."})
            self._send(404, {"error": "없는 주소입니다."})

        def do_POST(self) -> None:  # noqa: N802
            if not self._allowed():
                return self._send(401, {"error": "인증이 필요합니다."})
            if urlparse(self.path).path in ("/reviews/reopen", "/benefit-reviews/reopen"):
                body = self._body()
                if body is None:
                    return self._send(400, {"error": "본문은 5MB 이하의 JSON 객체여야 하고, note·reviewer는 글자여야 합니다."})
                reopen = service.reopen if urlparse(self.path).path == "/reviews/reopen" else service.benefit_reopen
                return self._send(*reopen(body))
            benefit = BENEFIT_REVIEW_PATH.match(urlparse(self.path).path)
            if benefit and benefit[2]:
                review_id = self._job_id(benefit)
                if review_id is None:
                    return self._send(400, {"error": "검수 ID 형식이 아닙니다."})
                body = self._body()
                if body is None:
                    return self._send(400, {"error": "본문은 5MB 이하의 JSON 객체여야 하고, note·reviewer는 글자여야 합니다."})
                return self._send(*service.benefit_decide(review_id, "APPROVED" if benefit[2] == "approve" else "REJECTED", body))
            match = REVIEW_PATH.match(urlparse(self.path).path)
            if not match or not match[2]:
                return self._send(404, {"error": "없는 주소입니다."})
            job_id = self._job_id(match)
            if job_id is None:
                return self._send(400, {"error": "작업 ID 형식이 아닙니다."})
            body = self._body()
            if body is None:
                return self._send(400, {"error": "본문은 5MB 이하의 JSON 객체여야 하고, note·reviewer는 글자여야 합니다."})
            action = service.approve if match[2] == "approve" else service.reject
            self._send(*action(job_id, body))

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - 기본 접근 로그 대신 JSON 로그만 씁니다
            return

    return Handler


def serve(service: ReviewService, host: str, port: int, token: str | None = None, health: Any = None) -> ThreadingHTTPServer:
    if not token and host not in LOOPBACK and host != "localhost":
        log.warning("검수 API 토큰(EXTRACTION_REVIEW_TOKEN)이 없어 같은 컴퓨터에서 온 요청만 받습니다", extra={"host": host})
    server = ThreadingHTTPServer((host, port), handler_for(service, token, health))
    return server
