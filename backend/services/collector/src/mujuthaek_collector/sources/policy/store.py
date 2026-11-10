"""정책 전용 저장. 게시판 수집(raw_posts …)과 테이블을 나눠요 (V202610220910__collector_policy_tables.sql).

raw_policies         정책 한 건. 6개 API의 칸을 통일한 값(제목·기관·지역·분야·주소·수정일) + 목록 응답 원본(list_raw)
raw_policy_versions  내용이 바뀔 때마다 한 줄. 통일한 내용 칸(지원대상·선정기준·지원내용·신청방법·신청기간·제출서류·나이)
                     + 목록·상세 응답 원본(api_raw) + 첨부·원문 상태 + AI에 넘긴 전체 글자
raw_policy_files     버전의 첨부 (S3 원본 위치, 역할 POLICY_DOC·ATTACHMENT, 찾은 곳 API·ORIGIN_PAGE)
raw_policy_texts     첨부에서 뽑은 글자 (원본 파일을 지워도 남겨요)
outbox               게시판 수집과 같이 써요. 새 버전마다 raw.policy.collected 이벤트 한 건
분류(raw_policies.field)는 BENEFIT·STARTUP_SUPPORT(지원 정책)와 SPACE_RECRUITMENT(사업공간 모집). 원본은 한 테이블에 두고 이 칸으로 나눠요
수집 회차(crawl_runs)도 게시판 수집과 같이 써요.
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field as dc_field
from datetime import date
from typing import Any, Protocol
from uuid import UUID

from mujuthaek_collector.core.storage import MAX_ATTEMPTS, Intake, PostgresStore, SavedFile
from mujuthaek_platform import outbox
from mujuthaek_platform.ids import uuid7

# 첨부(document_status)·원문 본문(origin_status) 상태. '없음'을 null 하나로 두면 이유를 잃어서 나눠 둬요
OK = "OK"  # 첨부 글자 / 원문 본문이 있어요
NONE = "NONE"  # 확인했는데 없어요 (원문 화면에 첨부 링크가 없음, 화면이 정책과 무관함, 서식·포스터만 있음)
NO_SOURCE = "NO_SOURCE"  # 볼 곳이 없어요 (API 첨부도 원문 주소도 없음)
BLOCKED = "BLOCKED"  # robots.txt 금지·403·429라 열지 않았어요
FAILED = "FAILED"  # 열거나 받거나 글자를 뽑다가 실패했어요 (연결 오류, 스캔 PDF …)
NOT_OPENED = "NOT_OPENED"  # 원문을 열지 않았어요 (API가 첨부를 줘서, 또는 첨부를 보지 않는 정책이라서)
NOT_NEEDED = "NOT_NEEDED"  # 첨부를 보지 않았어요: API 설명 칸으로 충분한 출처·정책 (PolicySource.attachments, AI 비용을 아끼려고)


@dataclass
class PolicyRow:
    id: UUID
    source_code: str
    policy_id: str  # 출처 안에서 유일 (보조금24 서비스ID, 복지로 servId, 온통청년 plcyNo)
    title: str
    marker: str  # 바뀌었는지 보는 값: 수정일, 없으면 목록 항목 해시
    list_raw: dict[str, Any]  # 목록 응답 한 건 그대로
    status: str  # SKIPPED, PENDING, DONE, FAILED, 처음 수집 개수 제한의 HELD·IGNORED
    attempts: int = 0
    last_error: str | None = None
    latest_version: int = 0
    field: str = "BENEFIT"  # 분류 (BENEFIT, STARTUP_SUPPORT, SPACE_RECRUITMENT). 목록 단계에서 정해 저장만 해요 (queued_policies는 읽지 않음)
    listed_on: date | None = None  # 목록의 등록일 (처음 수집 개수 제한, 저장만 해요)


@dataclass
class PolicyFields:
    """6개 API의 칸을 통일한 값. 출처에 없는 칸은 None이에요 (원본은 api_raw에 그대로 있어요)."""

    # raw_policies (정책 정보)
    title: str
    summary: str | None = None
    agency: str | None = None
    region_scope: str = "UNKNOWN"
    region_names: list[str] = dc_field(default_factory=list)
    region_codes: list[str] = dc_field(default_factory=list)
    field: str = "BENEFIT"
    categories: list[str] = dc_field(default_factory=list)
    detail_url: str | None = None
    apply_url: str | None = None
    source_modified_at: str | None = None
    # raw_policy_versions (내용). 글로 오는 칸은 원문 그대로, 날짜·금액으로 바꾸는 건 AI 추출 단계가 해요
    target: str | None = None  # 지원 대상
    criteria: str | None = None  # 선정 기준
    benefit: str | None = None  # 지원 내용
    how_to_apply: str | None = None  # 신청 방법
    apply_period: str | None = None  # 신청 기간·기한
    documents: str | None = None  # 제출 서류
    age_min: int | None = None  # API가 나이를 숫자로 줄 때만 (보조금24 지원조건, 온통청년)
    age_max: int | None = None


@dataclass
class PolicyFile(SavedFile):
    found_on: str = "API"  # API, ORIGIN_PAGE


@dataclass
class NewPolicyVersion:
    policy: PolicyRow
    version: int
    content_hash: str
    fields: PolicyFields
    api_raw: dict[str, Any]  # 목록 + 상세 + 지원조건 응답을 합친 원본
    body_text: str  # 버전 비교에 쓴 API 항목 글자
    full_text: str  # AI 추출에 넘긴 전체 글자
    document_status: str
    origin_status: str
    origin_checked: list[str] = dc_field(default_factory=list)  # 연 원문 주소
    origin_text_url: str | None = None  # 본문을 쓴 원문 주소
    run_id: UUID | None = None
    files: list[PolicyFile] = dc_field(default_factory=list)
    event: dict[str, Any] | None = None


@dataclass
class KnownPolicy:
    id: UUID
    marker: str
    status: str


class PolicyStore(Protocol):
    def start_run(self, source_code: str) -> UUID: ...
    def finish_run(self, run_id: UUID, status: str, new_count: int, warnings: list[str]) -> None: ...
    def known_policies(self, source_code: str) -> dict[str, KnownPolicy]: ...
    def insert_policy(self, policy: PolicyRow) -> None: ...
    def requeue_policy(self, policy_id: UUID, title: str, marker: str, list_raw: dict[str, Any], field: str, status: str = "PENDING") -> None: ...
    def skip_policy(self, policy_id: UUID, title: str, marker: str, list_raw: dict[str, Any], field: str) -> None: ...
    def queued_policies(self, source_code: str, limit: int) -> list[PolicyRow]: ...
    def latest_hash(self, policy_id: UUID) -> tuple[int, str, str] | None: ...
    def latest_files(self, policy_id: UUID) -> list[PolicyFile]: ...
    def mark_done(self, policy_id: UUID) -> None: ...
    def mark_failed(self, policy_id: UUID, error: str) -> None: ...
    def save_version(self, new: NewPolicyVersion) -> None: ...
    def expired_files(self, today: date, limit: int = 500) -> list[tuple[UUID, str]]: ...
    def mark_file_deleted(self, file_id: UUID) -> None: ...
    def intake(self, group: str) -> Intake | None: ...


POLICY_COLUMNS = "id, source_code, policy_id, title, marker, list_raw, status, attempts, last_error, latest_version"


class PostgresPolicyStore(PostgresStore):
    """수집 회차(start_run·finish_run)는 게시판 수집과 같은 crawl_runs를 써요. 나머지는 정책 전용 테이블이에요."""

    def known_policies(self, source_code: str) -> dict[str, KnownPolicy]:
        """출처의 정책을 한 번에 읽어요. 보조금24는 1만 건이 넘어서 한 건씩 찾으면 느려요."""
        rows = self.conn.execute("select policy_id, id, marker, status from raw_policies where source_code = %s", (source_code,)).fetchall()
        return {key: KnownPolicy(row_id, marker, status) for key, row_id, marker, status in rows}

    def insert_policy(self, policy: PolicyRow) -> None:
        self.conn.execute(
            "insert into raw_policies (id, source_code, policy_id, title, marker, list_raw, status, field, listed_on, last_error) "
            "values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) on conflict (source_code, policy_id) do nothing",
            (
                policy.id,
                policy.source_code,
                policy.policy_id,
                policy.title,
                policy.marker,
                self._json(policy.list_raw),
                policy.status,
                policy.field,
                policy.listed_on,
                policy.last_error,
            ),
        )

    def _set_list(self, policy_id: UUID, title: str, marker: str, list_raw: dict[str, Any], status: str, field: str) -> None:
        self.conn.execute(
            "update raw_policies set title = %s, marker = %s, list_raw = %s, status = %s, field = %s, attempts = 0, last_error = null, "
            "updated_at = now() where id = %s",
            (title, marker, self._json(list_raw), status, field, policy_id),
        )

    def requeue_policy(self, policy_id: UUID, title: str, marker: str, list_raw: dict[str, Any], field: str, status: str = "PENDING") -> None:
        """목록에서 바뀐 정책(수정일·항목이 달라짐)을 다시 열도록 PENDING으로 돌려요. 처음 수집을 고르기 전이면 HELD로 둬요."""
        self._set_list(policy_id, title, marker, list_raw, status, field)

    def skip_policy(self, policy_id: UUID, title: str, marker: str, list_raw: dict[str, Any], field: str) -> None:
        """1차 거름에 걸리지 않은 정책을 SKIPPED로 둬요. 목록 항목은 새 값으로 바꿔서 다음 판단에 써요."""
        self._set_list(policy_id, title, marker, list_raw, "SKIPPED", field)

    def queued_policies(self, source_code: str, limit: int) -> list[PolicyRow]:
        rows = self.conn.execute(
            f"select {POLICY_COLUMNS} from raw_policies where source_code = %s "
            "and (status = 'PENDING' or (status = 'FAILED' and attempts < %s)) order by (status = 'PENDING') desc, created_at limit %s",
            (source_code, MAX_ATTEMPTS, limit),
        ).fetchall()
        return [PolicyRow(*row) for row in rows]

    def latest_hash(self, policy_id: UUID) -> tuple[int, str, str] | None:
        """마지막 버전 (번호, 비교 해시, 원문 본문 상태)."""
        row = self.conn.execute(
            "select version, content_hash, origin_status from raw_policy_versions where raw_policy_id = %s order by version desc limit 1",
            (policy_id,),
        ).fetchone()
        return (row[0], row[1], row[2]) if row else None

    def latest_files(self, policy_id: UUID) -> list[PolicyFile]:
        """마지막 버전의 첨부(원본이 남아 있는 것)와 그 글자. 첨부를 끝내 받지 못할 때 이전 것을 이어 쓰는 데 써요(게시판 수집과 같음)."""
        rows = self.conn.execute(
            "select f.idx, f.name, f.role, f.download_url, f.file_hash, f.size_bytes, f.s3_key, f.stored_until, f.text_status, t.text, "
            "f.found_on from raw_policy_files f join raw_policy_versions v on v.id = f.version_id "
            "left join raw_policy_texts t on t.file_id = f.id "
            "where v.raw_policy_id = %s and v.version = (select max(version) from raw_policy_versions where raw_policy_id = %s) "
            "and f.s3_key is not null and f.deleted_at is null order by f.idx",
            (policy_id, policy_id),
        ).fetchall()
        return [PolicyFile(*row) for row in rows]

    def mark_done(self, policy_id: UUID) -> None:
        # 실패 횟수도 되돌려요(게시판 수집과 같음, 2026-11-10 재검토)
        self.conn.execute("update raw_policies set status = 'DONE', attempts = 0, last_error = null, updated_at = now() where id = %s", (policy_id,))

    def mark_failed(self, policy_id: UUID, error: str) -> None:
        self.conn.execute(
            "update raw_policies set status = 'FAILED', attempts = attempts + 1, last_error = %s, updated_at = now() where id = %s",
            (error[:2000], policy_id),
        )

    def save_version(self, new: NewPolicyVersion) -> None:
        """버전 + 첨부 + 첨부 글자 + 정책의 통일 칸 + 상태 + 아웃박스 이벤트를 한 트랜잭션으로."""
        version_id, f = uuid7(), new.fields
        with self.conn.transaction(), self.conn.cursor() as cur:
            cur.execute(
                "insert into raw_policy_versions (id, raw_policy_id, version, content_hash, target, criteria, benefit, how_to_apply, "
                "apply_period, documents, age_min, age_max, api_raw, document_status, origin_status, origin_checked, origin_text_url, "
                "body_text, full_text, crawl_run_id) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    version_id,
                    new.policy.id,
                    new.version,
                    new.content_hash,
                    f.target,
                    f.criteria,
                    f.benefit,
                    f.how_to_apply,
                    f.apply_period,
                    f.documents,
                    f.age_min,
                    f.age_max,
                    self._json(new.api_raw),
                    new.document_status,
                    new.origin_status,
                    self._json(new.origin_checked),
                    new.origin_text_url,
                    new.body_text,
                    new.full_text,
                    new.run_id,
                ),
            )
            for file in new.files:
                file_id = uuid7()
                cur.execute(
                    "insert into raw_policy_files (id, version_id, idx, name, role, found_on, download_url, file_hash, size_bytes, s3_key, "
                    "stored_until, text_status) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (
                        file_id,
                        version_id,
                        file.idx,
                        file.name,
                        file.role,
                        file.found_on,
                        file.download_url,
                        file.file_hash,
                        file.size_bytes,
                        file.s3_key,
                        file.stored_until,
                        file.text_status,
                    ),
                )
                if file.text:
                    cur.execute("insert into raw_policy_texts (id, file_id, text) values (%s, %s, %s)", (uuid7(), file_id, file.text))
            cur.execute(
                "update raw_policies set summary = %s, agency = %s, region_scope = %s, region_names = %s, region_codes = %s, field = %s, "
                "categories = %s, detail_url = %s, apply_url = %s, source_modified_at = %s, status = 'DONE', latest_version = %s, "
                "attempts = 0, last_error = null, updated_at = now() where id = %s",
                (
                    f.summary,
                    f.agency,
                    f.region_scope,
                    f.region_names,
                    f.region_codes,
                    f.field,
                    f.categories,
                    f.detail_url,
                    f.apply_url,
                    f.source_modified_at,
                    new.version,
                    new.policy.id,
                ),
            )
            if new.event is not None:
                outbox.add(cur, new.event)

    # ── 보관 기한 정리 (cleanup 명령) ───────────────────────────
    def expired_files(self, today: date, limit: int = 500) -> list[tuple[UUID, str]]:
        rows = self.conn.execute(
            "select id, s3_key from raw_policy_files where stored_until < %s and s3_key is not null and deleted_at is null limit %s", (today, limit)
        ).fetchall()
        return [(r[0], r[1]) for r in rows]

    def mark_file_deleted(self, file_id: UUID) -> None:
        self.conn.execute("update raw_policy_files set s3_key = null, deleted_at = now() where id = %s", (file_id,))
