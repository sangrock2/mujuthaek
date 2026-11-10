"""정책 API 출처 하나를 끝까지 수집해요 (게시판 수집 pipeline.py와 같은 흐름).

run_policy_source
  ├─ 목록 전체 읽기 (sync_list, 구간이 있으면 구간마다) → source.fetch_list
  │    처음 본 정책 → 1차 거름(source.wanted)에 걸리고 신청이 끝나지 않았으면(source.closed) PENDING, 아니면 SKIPPED
  │    (처음 수집 개수 제한: 고르기 전이면 PENDING 대신 HELD, 고른 뒤 기준일보다 오래되면 IGNORED. core/intake.py)
  │    분류(source.classify)도 여기서 정해 raw_policies.field에 둬요: 지원 정책(BENEFIT·STARTUP_SUPPORT) / 사업공간 모집(SPACE_RECRUITMENT)
  │    이미 본 정책 → 수정일(또는 목록 항목 해시)이 바뀌면 다시 PENDING. 거름은 회차마다 다시 판단해요
  └─ 밀린 정책(PENDING·FAILED)을 한 번에 detail_limit건까지 처리 (process_policy)
       상세를 한꺼번에 받을 수 있는 출처(보조금24)는 먼저 받아 둠 (source.prefetch)
       상세 (source.fetch_detail) → 첨부: API가 준 설명 문서, 없으면(서식뿐이어도) 원문 화면에서 찾기 → 받기·글자 뽑기
       → 버전 비교(항목 + 첨부 해시) → S3 원본 → 저장 + raw.policy.collected 이벤트 (한 트랜잭션)

오류 반응
  API 키·호출 한도 오류(BlockedError, HTTP 401 포함)  출처 회차 중단(BLOCKED). 밀린 정책은 다음 회차에 먼저 처리
  목록 페이지 실패·응답 모양 다름       목록 읽기를 멈추고 회차는 FAILED. 이미 쌓인 정책(PENDING·FAILED) 처리는 계속해요
  상세 API 실패·응답 모양 다름         그 정책만 FAILED (3번까지 다시 시도)
  원문·첨부 robots 금지·403·429·오류   그 화면·파일만 건너뛰고 정책은 저장. 막힌 도메인은 이번 회차에 다시 요청하지 않아요
"""

from __future__ import annotations

import dataclasses
import logging
import urllib.parse
from dataclasses import dataclass, field
from datetime import date
from uuid import UUID

import httpx

from mujuthaek_collector.core import intake
from mujuthaek_collector.core.documents.text import extract_text
from mujuthaek_collector.core.file_store import FileStore, add_months, content_type, object_key, text_key
from mujuthaek_collector.core.files import DOC_EXTS, FileRef
from mujuthaek_collector.core.publisher import MAX_TEXT_CHARS
from mujuthaek_collector.core.storage import DONE, FAILED, HELD, IGNORED, MAX_ATTEMPTS, PENDING, SKIPPED
from mujuthaek_collector.core.versioning import content_hash, sha256_hex
from mujuthaek_collector.errors import BlockedError, FileNotReady, FileRejected, FileUnavailable, ParseError
from mujuthaek_collector.pipeline import RunResult, transient
from mujuthaek_collector.sources.base import Fetcher
from mujuthaek_collector.sources.policy import store as st
from mujuthaek_collector.sources.policy.attachments import (
    MAIN_DOC,
    explains,
    file_links,
    focus,
    garbled,
    main_text,
    origin_file_ok,
    relevant,
    with_ext,
)
from mujuthaek_collector.sources.policy.base import SCOPE_LABELS, PolicyDetail, PolicyItem, PolicySource, shop_recruitment
from mujuthaek_collector.sources.policy.client import ApiError, MaskedFetcher, mask
from mujuthaek_collector.sources.policy.config import PolicySettings
from mujuthaek_collector.sources.policy.event import build_policy_event
from mujuthaek_collector.sources.policy.store import NewPolicyVersion, PolicyFields, PolicyFile, PolicyRow, PolicyStore
from mujuthaek_platform.ids import uuid7

log = logging.getLogger(__name__)
MAX_TEXT_DOCS = 1  # 글자를 뽑는 첨부 문서 수. 하나를 뽑으면 더 받지 않아요 (AI 비용·수집 시간)


@dataclass
class PolicyContext:
    source: PolicySource
    api: Fetcher
    web: Fetcher
    store: PolicyStore
    files: FileStore
    settings: PolicySettings
    today: date
    run_id: UUID
    result: RunResult
    blocked_hosts: set[str] = field(default_factory=set)  # 이번 회차에 다시 요청하지 않을 원문·첨부 도메인
    noted: set[str] = field(default_factory=set)

    def warn(self, message: str) -> None:
        message = mask(message, self.source.secrets())
        log.warning(message, extra={"source": self.source.code})
        self.result.warnings.append(message)

    def warn_once(self, key: str, message: str) -> None:
        """같은 이유(도메인 차단 등)는 회차에 한 번만 남겨요. 보조금24는 1만 건이 모두 같은 이유로 막혀서요."""
        if key not in self.noted:
            self.noted.add(key)
            self.warn(message)


def run_policy_source(
    source: PolicySource,
    api: Fetcher,
    web: Fetcher,
    store: PolicyStore,
    files: FileStore,
    settings: PolicySettings,
    *,
    recheck: bool = False,
    today: date | None = None,
) -> RunResult:
    """정책 출처 하나를 수집해요. api는 API 요청용, web은 원문 화면·첨부용(robots.txt를 지키는 PoliteClient)이에요.
    recheck=True면 목록에서 바뀌지 않은 정책도 다시 열어봐요 (상세나 첨부만 바뀐 경우를 찾으려고)."""
    result = RunResult(source.code)
    run_id = store.start_run(source.code)
    ctx = PolicyContext(source, MaskedFetcher(api, source.secrets()), web, store, files, settings, today or date.today(), run_id, result)
    log.info("정책 수집 시작", extra={"source": source.code, "recheck": recheck})
    if not source.api_key:
        result.status = "FAILED"
        ctx.warn(f"{source.key_env} 환경 변수가 없어 {source.name}을(를) 수집하지 않았어요")
    else:
        try:
            sync_list(ctx, recheck=recheck)
            queue = store.queued_policies(source.code, settings.detail_limit)
            if queue:
                prefetch(ctx, queue)
            for policy in queue:
                process_safely(ctx, policy)
        except BlockedError as error:
            result.status = "BLOCKED"
            ctx.warn(f"API가 막혀 이번 회차를 멈춰요: {error}")
        except Exception as error:  # noqa: BLE001 — 예상 못한 오류도 회차 기록은 남겨요
            result.status = "FAILED"
            ctx.warn(f"예상 못한 오류: {type(error).__name__}: {error}")
            log.error("정책 수집 실패", extra={"source": source.code, "error": mask(repr(error), source.secrets())})
    store.finish_run(run_id, result.status, result.new_count, result.warnings)
    log.info("정책 수집 끝", extra={"source": source.code, "status": result.status, "new": result.new_count})
    return result


# ── 목록 ───────────────────────────────────────────────────────
def sync_list(ctx: PolicyContext, *, recheck: bool = False) -> None:
    """목록 전체를 읽어 새 정책·바뀐 정책을 PENDING으로, 1차 거름에 걸리지 않은 정책을 SKIPPED로 둬요. 상세는 여기서 열지 않아요."""
    source, store = ctx.source, ctx.store
    known = store.known_policies(source.code)
    seen: set[str] = set()
    added = changed = skipped = dropped = 0
    for segment in source.segments():
        label = f"{source.name}{f' [{segment}]' if segment else ''}"
        fetched = 0
        for page in range(1, ctx.settings.max_pages + 1):
            try:
                result = source.fetch_list(ctx.api, page, segment)
            except (ParseError, ApiError) as error:
                # 목록을 끝까지 못 읽으면 이번 회차에 새로 올라온 정책을 놓쳐요. 회차는 FAILED로 남기고, 이미 쌓인 정책 처리는 계속해요
                ctx.result.status = "FAILED"
                ctx.warn(f"{label} 목록 {page}페이지를 읽지 못해 목록 읽기를 멈춰요: {error}")
                break
            if page == 1 and not result.count:
                ctx.warn(f"{label} 목록이 비어 있어요 (API 응답 모양이나 검색 조건 확인)")
            dropped += result.count - len(result.items)
            for item in result.items:
                if item.policy_id in seen:
                    continue
                seen.add(item.policy_id)
                entry = known.get(item.policy_id)
                # 상가 모집은 수집하지 않아요 (base.SHOP_RECRUIT)
                wanted = source.wanted(item) and not shop_recruitment(item.title) and not source.closed(item, ctx.today)
                kind = source.classify(item.title, item.record)  # 지원 정책(BENEFIT·STARTUP_SUPPORT) / 사업공간 모집(SPACE_RECRUITMENT)
                if entry is None:
                    register(ctx, item, opened(ctx, item, kind) if wanted else SKIPPED, kind)
                    added += wanted
                    skipped += not wanted
                elif entry.status == IGNORED or (entry.status == HELD and wanted):
                    continue  # 처음 수집 개수 제한에서 빠진 정책은 다시 보지 않고, 고르기 전인 정책은 그대로 기다려요
                elif not wanted:
                    # 기다리던 정책과 바뀐 정책은 SKIPPED로. 이미 수집한(DONE) 정책은 목록이 바뀔 때까지 그대로 둬요
                    if entry.status in (PENDING, FAILED, HELD) or entry.marker != item.marker:
                        store.skip_policy(entry.id, item.title, item.marker, item.record, kind)
                        skipped += 1
                elif entry.status == SKIPPED or entry.marker != item.marker or (recheck and entry.status == DONE):
                    # 걸러졌던 정책이 다시 열 정책이 되면 새로 본 정책처럼 처음 수집 개수 제한을 따라요
                    status = opened(ctx, item, kind) if entry.status == SKIPPED else PENDING
                    store.requeue_policy(entry.id, item.title, item.marker, item.record, kind, status)
                    changed += status == PENDING
            # 페이지 넘김은 응답에 온 항목 수로 판단해요 (ID가 없어 버린 항목 포함)
            fetched += result.count
            if not result.count or result.count < source.page_size or (result.total is not None and fetched >= result.total):
                break
        else:
            ctx.warn(f"{label} 목록이 {ctx.settings.max_pages}페이지를 넘어서 나머지는 읽지 않았어요")
    if dropped:
        ctx.warn(f"{source.name} 목록에서 정책 ID가 없는 항목 {dropped}건을 건너뛰었어요 (API 응답 확인)")
    log.info("정책 목록", extra={"source": source.code, "listed": len(seen), "new": added, "changed": changed, "skipped": skipped})


def opened(ctx: PolicyContext, item: PolicyItem, kind: str) -> str:
    """열 정책의 상태: 처음 수집을 고르기 전이면 HELD, 기준일보다 오래되면 IGNORED, 아니면 PENDING (core/intake.py)."""
    return intake.open_status(ctx.store, intake.policy_group(kind), ctx.source.listed_on(item.record))


def register(ctx: PolicyContext, item: PolicyItem, status: str = PENDING, kind: str | None = None) -> None:
    kind = kind or ctx.source.classify(item.title, item.record)
    row = PolicyRow(uuid7(), ctx.source.code, item.policy_id, item.title, item.marker, item.record, status, field=kind)
    row.listed_on = ctx.source.listed_on(item.record)
    row.last_error = intake.IGNORED_REASON if status == IGNORED else None
    ctx.store.insert_policy(row)


def prefetch(ctx: PolicyContext, queue: list[PolicyRow]) -> None:
    """상세를 한꺼번에 받을 수 있는 출처(보조금24)는 미리 받아 둬요. 실패하면 정책마다 받아요."""
    try:
        ctx.source.prefetch(ctx.api, [policy.policy_id for policy in queue])
    except (ParseError, ApiError) as error:
        ctx.warn(f"{ctx.source.name} 상세를 한꺼번에 받지 못해 정책마다 받아요: {error}")


# ── 정책 하나 ──────────────────────────────────────────────────
def process_safely(ctx: PolicyContext, policy: PolicyRow) -> None:
    try:
        if process_policy(ctx, policy):
            ctx.result.new_count += 1
    except BlockedError:
        raise  # API 키·한도 문제. 이 정책은 PENDING·FAILED 그대로 남아 다음 회차에 먼저 처리돼요
    except FileUnavailable as error:
        # 첨부 일시 오류: 그 파일 없이 새 버전을 만들지 않고 실패로 세어 다음 회차에 다시 받아요(게시판 수집과 같음). 예전엔 연결 오류 한 번에
        # 버전이 v1(첨부 있음) → v2(첨부 없음) → v3(첨부 있음)으로 오락가락해 추출·알림이 다시 돌았어요(2026-11-10 재검토)
        ctx.store.mark_failed(policy.id, mask(f"FileUnavailable: {error}", ctx.source.secrets()))
        ctx.warn(f"[{policy.policy_id}] {policy.title[:40]} — {error} 다음 회차에 다시 받아요")
    except (ParseError, ApiError) as error:
        ctx.store.mark_failed(policy.id, mask(f"{type(error).__name__}: {error}", ctx.source.secrets()))
        ctx.warn(f"[{policy.policy_id}] {policy.title[:40]} — 상세를 읽지 못했어요: {error}")
    except Exception as error:  # noqa: BLE001 — S3·DB 오류 등. 그 정책만 FAILED로 두고 다음으로 가요
        ctx.store.mark_failed(policy.id, mask(f"{type(error).__name__}: {error}", ctx.source.secrets()))
        ctx.warn(f"[{policy.policy_id}] {policy.title[:40]} — 저장하지 못했어요: {type(error).__name__}: {error}")


def process_policy(ctx: PolicyContext, policy: PolicyRow) -> bool:
    """상세 → 첨부 → 글자 → 버전 비교 → 저장·이벤트. 새 버전을 저장했으면 True."""
    source = ctx.source
    item = PolicyItem(policy.policy_id, policy.title, policy.marker, policy.list_raw)
    detail = source.fetch_detail(ctx.api, item)

    wants_documents = source.needs_documents(detail.record)
    candidates = [Candidate(f, "API", detail.detail_url) for f in detail.files] if wants_documents else []
    origin = OriginResult()
    if wants_documents and not any(explains(c.file) for c in candidates):  # API 첨부가 없거나 서식·포스터뿐이면 원문 화면에서 공고문을 찾아요
        origin = from_origin(ctx, detail, item.title)
        candidates += origin.candidates
    # 마지막 시도엔 다시 받지 않고, 받지 못한 첨부는 이전 버전의 같은 첨부(주소, 없으면 이름)를 이어 써요(없으면 그 파일 없이)
    retry_later = policy.attempts + 1 < MAX_ATTEMPTS
    earlier = [] if retry_later or not policy.latest_version else ctx.store.latest_files(policy.id)
    saved = collect_files(ctx, candidates, retry_later=retry_later, earlier=earlier)

    body = source.body_text(detail.record)
    # 원문 화면 글자는 비교에서 빼요. 조회수·방문자 수·오늘 날짜가 섞여 있어서, 넣으면 열 때마다 새 버전이 돼요
    new_hash = content_hash(body, [f.file_hash for f, _ in saved])
    latest = ctx.store.latest_hash(policy.id)
    # 원문 본문을 처음 얻었으면 내용이 같아도 새 버전을 만들어요 (지난 버전엔 원문 본문이 없었음: 원문을 새로 읽게 된 출처 등)
    gained_origin = origin.text is not None and latest is not None and latest[2] != st.OK
    if latest and latest[1] == new_hash and not gained_origin:
        ctx.store.mark_done(policy.id)  # 목록 수정일만 바뀌고 내용은 같음
        return False
    version = (latest[0] if latest else 0) + 1

    for f, data in saved:  # 원본은 DB 트랜잭션 전에 S3에 올려요 (실패하면 그 정책은 다음 회차에 다시 시도)
        if data is None:  # 이어 쓴 이전 첨부: 원본·보관 기한을 그대로 함께 써요
            continue
        f.s3_key = ctx.files.put(object_key(source.code, policy.policy_id, version, f.idx, f.name), data, content_type(FileRef(f.name, "", 0).ext))

    fields = policy_fields(source, item, detail)
    origin_state = origin_status(detail, origin)
    document_state = document_status(candidates, saved, origin_state) if wants_documents else st.NOT_NEEDED
    full_text = compose_full_text(source, policy, detail, source.ai_text(detail.record), saved, origin.text)
    long_text_key = None
    if len(full_text) > MAX_TEXT_CHARS:
        long_text_key = ctx.files.put(text_key(source.code, policy.policy_id, version), full_text.encode("utf-8"), content_type("txt"))

    event = build_policy_event(
        raw_policy_id=policy.id,
        version=version,
        source_code=source.code,
        provider=source.provider,
        field=fields.field,
        policy_id=policy.policy_id,
        title=item.title,
        agency=detail.agency,
        region_scope=detail.region_scope,
        region_names=detail.region_names,
        region_codes=detail.region_codes,
        categories=detail.categories,
        detail_url=detail.detail_url,
        apply_url=detail.apply_url,
        source_modified_at=detail.modified_at,
        full_text=full_text,
        text_key=long_text_key,
        record=detail.record,
        has_document=document_state == st.OK,
        has_origin_text=origin.text is not None,
        document_status=document_state,
        origin_status=origin_state,
        files=[
            {
                "name": f.name,
                "fileType": FileRef(f.name, "", 0).ext,  # pdf, hwp, hwpx (설명 문서만 받아요. with_ext가 확장자를 맞춰 둬요)
                "role": f.role,
                "s3Key": f.s3_key,
                "downloadUrl": f.download_url,
                "sha256": f.file_hash,
                "foundOn": f.found_on,
            }
            for f, _ in saved
        ],
    )
    ctx.store.save_version(
        NewPolicyVersion(
            policy=policy,
            version=version,
            content_hash=new_hash,
            fields=fields,
            api_raw=detail.record,
            body_text=body,
            full_text=full_text,
            document_status=document_state,
            origin_status=origin_state,
            origin_checked=origin.checked,
            origin_text_url=origin.text.url if origin.text else None,
            run_id=ctx.run_id,
            files=[f for f, _ in saved],
            event=event,
        )
    )
    log.info("정책 새 버전 저장", extra={"source": source.code, "policy": policy.policy_id, "version": version, "files": len(saved)})
    return True


def policy_fields(source: PolicySource, item: PolicyItem, detail: PolicyDetail) -> PolicyFields:
    """출처마다 다른 칸 → 통일한 칸 (raw_policies·raw_policy_versions)."""
    return PolicyFields(
        title=item.title,
        summary=detail.summary,
        agency=detail.agency,
        region_scope=detail.region_scope,
        region_names=detail.region_names,
        region_codes=detail.region_codes,
        field=source.classify(item.title, detail.record),
        categories=detail.categories,
        detail_url=detail.detail_url,
        apply_url=detail.apply_url,
        source_modified_at=detail.modified_at,
        target=detail.target,
        criteria=detail.criteria,
        benefit=detail.benefit,
        how_to_apply=detail.how_to_apply,
        apply_period=detail.apply_period,
        documents=detail.documents,
        age_min=detail.age_min,
        age_max=detail.age_max,
    )


def origin_status(detail: PolicyDetail, origin: OriginResult) -> str:
    """원문 화면 본문 상태. 원문을 아예 안 연 경우(API 첨부가 있음)와 볼 곳이 없는 경우를 나눠요."""
    if not origin.opened:
        return st.NOT_OPENED
    if origin.text:
        return st.OK
    if origin.checked:
        return st.NONE  # 열었지만 본문이 없거나 정책과 무관한 화면
    if not detail.origin_urls:
        return st.NO_SOURCE
    return st.BLOCKED if origin.blocked else st.FAILED


def document_status(candidates: list[Candidate], saved: list[tuple[PolicyFile, bytes]], origin_state: str) -> str:
    """첨부 글자 상태. 첨부가 없으면 원문 상태를 따라가요 (원문이 막혔으면 첨부도 확인 못 한 거라서)."""
    if any(f.role == "POLICY_DOC" for f, _ in saved):
        return st.OK
    if not candidates:
        return origin_state if origin_state in (st.NO_SOURCE, st.BLOCKED, st.FAILED) else st.NO_SOURCE if origin_state == st.NOT_OPENED else st.NONE
    # 공고·안내 문서 후보가 있었는데 글자가 없으면 받기·글자 뽑기 실패, 서식·포스터만 있었으면 없음
    return st.FAILED if any(explains(c.file) for c in candidates) else st.NONE


# ── 원문 화면 ──────────────────────────────────────────────────
@dataclass
class OriginText:
    url: str
    text: str


@dataclass
class OriginResult:
    opened: bool = False  # 원문을 열어 보려고 했는지 (API가 첨부를 주면 열지 않아요)
    candidates: list[Candidate] = field(default_factory=list)
    checked: list[str] = field(default_factory=list)  # 연 주소
    text: OriginText | None = None
    blocked: int = 0  # robots.txt 금지·403·429
    failed: int = 0  # 연결 오류 등


def from_origin(ctx: PolicyContext, detail: PolicyDetail, title: str) -> OriginResult:
    """API에 첨부가 없을 때: 원문 화면을 차례로 열어 첨부 링크와 본문 글자를 찾아요.
    첨부는 링크가 있는 첫 화면의 것을, 본문은 정책 이름과 관련 있는 첫 화면의 것을 써요.
    첨부 링크는 attachments.origin_file_ok로 걸러요: 사이트 공통 정적 파일(접근성 인증서·전화번호부 …)과,
    정책과 관련 없는 화면(사이트 첫 화면)에서 이름이 정책과 무관한 파일은 빼요."""
    result = OriginResult(opened=True)
    for url in list(dict.fromkeys(detail.origin_urls))[: ctx.settings.max_origin_pages]:
        host = urllib.parse.urlsplit(url).netloc
        if not host:
            continue
        if host in ctx.blocked_hosts:
            result.blocked += 1
            continue
        try:
            html = ctx.web.text(url)
        except BlockedError as error:  # robots.txt 금지·403·429·대기실: 이 도메인은 이번 회차에 더 묻지 않아요
            ctx.blocked_hosts.add(host)
            ctx.warn_once(f"blocked:{host}", f"원문을 열지 않았어요 ({host}): {error}")
            result.blocked += 1
            continue
        except (httpx.HTTPError, FileRejected) as error:
            ctx.warn(f"원문을 열지 못했어요 ({url}): {error}")
            result.failed += 1
            continue
        result.checked.append(url)
        text = without_nul(main_text(html))
        page_relevant = bool(text and relevant(title, text))
        if result.text is None and page_relevant:
            result.text = OriginText(url, text)
        links = (
            [f for f in file_links(html, url) if origin_file_ok(f, title, page_relevant)] if ctx.source.origin_files else []
        )  # 첫 화면·하단 공통 링크는 빼요
        result.candidates += [Candidate(f, "ORIGIN_PAGE", url) for f in links]
        if any(explains(f) for f in links):
            return result  # 공고문이 있는 첫 화면까지만 열어요
    return result


# ── 첨부 ──────────────────────────────────────────────────────
@dataclass
class Candidate:
    file: FileRef
    found_on: str  # API, ORIGIN_PAGE
    referer: str | None


def rank(candidates: list[Candidate]) -> list[Candidate]:
    """받을 첨부와 순서: 설명 문서(attachments.explains)만, 공고·안내·지침 이름이 먼저. 같은 주소는 한 번만.
    신청서·서식·포스터·명단은 AI 추출에 쓸모가 없어서 받지 않아요."""
    unique = list({c.file.url: c for c in candidates if explains(c.file)}.values())
    return sorted(unique, key=lambda c: (not MAIN_DOC.search(c.file.name), c.file.ext not in ("pdf", ""), c.file.index))


def collect_files(
    ctx: PolicyContext, candidates: list[Candidate], *, retry_later: bool = False, earlier: list[PolicyFile] | None = None
) -> list[tuple[PolicyFile, bytes | None]]:
    """설명 문서를 순서대로(rank) 받아 글자를 뽑고, MAX_TEXT_DOCS개를 뽑으면 멈춰요. 글자를 못 뽑은 문서(스캔본 등)는
    ATTACHMENT로 남기고 다음 문서를 봐요 (최대 max_files개). (저장 정보, 원본. 이어 쓴 이전 첨부는 원본 None)
    retry_later면 첨부 일시 오류를 FileUnavailable로 올려요. earlier(마지막 시도의 이전 버전 첨부)가 있으면 받지 못한 첨부를 이어 써요."""
    keep_until = add_months(ctx.today, ctx.settings.keep_months)
    saved: list[tuple[PolicyFile, bytes | None]] = []
    texts = 0
    for candidate in rank(candidates):
        if len(saved) >= ctx.settings.max_files or texts >= MAX_TEXT_DOCS:
            break
        before = _previous(earlier or [], candidate.file)
        try:
            data = download(ctx, candidate, retry_later=retry_later or before is not None)
        except FileUnavailable as error:
            if retry_later or before is None:
                raise
            ctx.warn(f"{error} 이전 버전의 같은 첨부를 이어 써요")
            texts += bool(before.text)
            saved.append((dataclasses.replace(before, idx=len(saved)), None))
            continue
        if data is None:
            continue
        file = with_ext(candidate.file, data)
        if file.ext not in DOC_EXTS:  # 확장자 없이 온 파일이 그림·압축·엑셀이었어요
            continue
        text, status = extract_text(data, file.ext)
        if garbled(text):
            text, status = None, "PDF 글자가 깨짐 (글꼴에 글자 정보 없음)"
        text = without_nul(text)
        if not text:
            ctx.warn(f"첨부 글자를 읽지 못했어요 ({file.name}): {status}")
        texts += bool(text)
        role = "POLICY_DOC" if text else "ATTACHMENT"  # 글자를 못 뽑은 설명 문서 (스캔본 등)
        saved.append((make_saved(len(saved), file, role, candidate.found_on, data, keep_until, status, text), data))
    return saved


def without_nul(text: str | None) -> str | None:
    """한글·PDF 문서에서 뽑은 글자에 NUL(\\x00)이 섞여 오기도 해요. PostgreSQL text 칸은 NUL을 받지 않아서 지워요 (2026-10-19 기업마당 첨부)."""
    return text.replace("\x00", "") if text else text


def _previous(earlier: list[PolicyFile], file: FileRef) -> PolicyFile | None:
    return next((f for f in earlier if f.download_url == file.url), None) or next((f for f in earlier if f.name == file.name), None)


def download(ctx: PolicyContext, candidate: Candidate, *, retry_later: bool = False) -> bytes | None:
    """첨부 원본. retry_later면 다음에 받아질 수 있는 오류(연결·5xx·점검 화면·robots.txt 잠시 못 받음)를 FileUnavailable로 올려요."""
    file = candidate.file
    host = urllib.parse.urlsplit(file.url).netloc
    if host in ctx.blocked_hosts:
        return None
    try:
        return ctx.web.download(file.url, referer=candidate.referer)
    except FileRejected as error:
        if retry_later and isinstance(error, FileNotReady):
            raise FileUnavailable(f"첨부를 잠시 받지 못했어요 ({file.name}): {error}.") from error
        ctx.warn(f"첨부를 받지 않았어요 ({file.name}): {error}")
    except BlockedError as error:
        ctx.blocked_hosts.add(host)
        ctx.warn_once(f"blocked:{host}", f"첨부 도메인이 막혀 받지 않았어요 ({host}): {error}")
    except httpx.HTTPError as error:
        if retry_later and transient(error):
            raise FileUnavailable(f"첨부를 잠시 받지 못했어요 ({file.name}): {error}.") from error
        ctx.warn(f"첨부를 받지 못했어요 ({file.name}): {error}")
    return None


def make_saved(idx: int, file: FileRef, role: str, found_on: str, data: bytes, keep_until: date, status: str | None, text: str | None) -> PolicyFile:
    return PolicyFile(
        idx=idx,
        name=file.name,
        role=role,
        download_url=file.url,
        file_hash=sha256_hex(data),
        size_bytes=len(data),
        s3_key=None,
        stored_until=keep_until,
        text_status=status,
        text=text,
        found_on=found_on,
    )


# ── AI에 넘길 글자 ─────────────────────────────────────────────
def compose_full_text(
    source: PolicySource, policy: PolicyRow, detail: PolicyDetail, body: str, saved: list[tuple[PolicyFile, bytes]], origin: OriginText | None = None
) -> str:
    """AI 추출(extraction)에 넘기는 전체 글자: 정책 정보 → API 설명 항목(source.ai_text) → 원문 화면 본문 → 첨부 문서 글자.
    정책 ID·주소·수정일은 이벤트의 다른 칸에 있어서 넣지 않아요."""
    region = f"{SCOPE_LABELS[detail.region_scope]} {', '.join(detail.region_names) if len(detail.region_names) <= 5 else ''}".rstrip()
    lines = [
        f"제목: {policy.title}",
        f"기관: {detail.agency or ''}",
        f"지역: {region}",
        f"분야: {', '.join(detail.categories)}",
        "[항목]",
        body or "(항목 없음)",
    ]
    if origin:
        lines += [f"[원문 화면: {origin.url}]", origin.text]
    for f, _ in saved:
        place = "API 첨부" if f.found_on == "API" else "원문 첨부"
        lines.append(f"[{place}: {f.name}]")
        if f.text:
            part = focus(f.text, policy.title)  # 긴 지침서는 이 정책 부분만 (전체 글자는 raw_policy_texts에 그대로 둬요)
            if part is None:
                lines.append(f"(문서가 길고({len(f.text):,}자) 정책 이름이 나오지 않아 글자를 넣지 않았어요)")
            elif part is not f.text:
                lines += [f"(긴 문서라 정책 관련 부분만 넣었어요: {len(f.text):,}자 중 {len(part):,}자)", part]
            else:
                lines.append(part)
    return "\n".join(lines)
