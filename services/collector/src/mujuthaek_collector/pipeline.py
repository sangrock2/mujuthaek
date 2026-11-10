"""출처 하나를 끝까지 수집해요 (전체 흐름 그대로).

run_source
  └─ 게시판마다
      ├─ 목록 1~N페이지 읽기 → 새 글 등록(분류) / 이미 본 글은 목록 상태만 갱신
      ├─ 밀린 글(PENDING·FAILED) + 새 글을 한 번에 detail_limit건까지 처리 (process_post)
      └─ 밀린 글이 없으면 목록 1페이지 해시 저장 (다음 회차에 같으면 바로 끝)

오류 반응: BlockedError → 그 글 FAILED + 출처 회차 중단(BLOCKED), ParseError·HTTP 오류 → 그 글만 FAILED, FileRejected → 그 파일만 건너뜀,
  FileUnavailable(첨부 일시 오류) → 새 버전을 만들지 않고 FAILED로 다시 시도. 마지막 시도엔 이전 버전의 같은 첨부를 이어 쓰고(처음 글은 그 파일 없이) 저장
"""

from __future__ import annotations

import dataclasses
import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from uuid import UUID

import httpx

from mujuthaek_collector.config import Settings
from mujuthaek_collector.core import classify as cls
from mujuthaek_collector.core import intake
from mujuthaek_collector.core.documents.text import extract_text
from mujuthaek_collector.core.file_store import FileStore, content_type, object_key, stored_until, text_key
from mujuthaek_collector.core.files import FileRef, pick_notice_files, pick_unit_lists, unclear_notice
from mujuthaek_collector.core.publisher import MAX_TEXT_CHARS, build_collected_event
from mujuthaek_collector.core.storage import IGNORED, MAX_ATTEMPTS, ORPHAN_FOLLOW_UP, PENDING, SKIPPED, BoardState, NewVersion, PostRow, SavedFile, Store
from mujuthaek_collector.core.versioning import content_hash, list_hash, sha256_hex
from mujuthaek_collector.errors import BlockedError, FileNotReady, FileRejected, FileUnavailable, ParseError
from mujuthaek_collector.sources.base import Board, Detail, Fetcher, ListItem, Source
from mujuthaek_platform.ids import uuid7

log = logging.getLogger(__name__)


@dataclass
class RunResult:
    source_code: str
    status: str = "SUCCESS"  # SUCCESS, BLOCKED, FAILED
    new_count: int = 0  # 새로 저장한 버전 수
    warnings: list[str] = field(default_factory=list)


@dataclass
class Context:
    source: Source
    client: Fetcher
    store: Store
    files: FileStore
    settings: Settings
    today: date
    run_id: UUID
    result: RunResult

    def warn(self, message: str) -> None:
        log.warning(message, extra={"source": self.source.code})
        self.result.warnings.append(message)


def run_source(
    source: Source, client: Fetcher, store: Store, files: FileStore, settings: Settings, *, recheck: bool = False, today: date | None = None
) -> RunResult:
    """출처 하나를 수집해요. recheck=True(새벽 정정 확인)면 마감 전 공고를 다시 열어 바뀌었는지 봐요."""
    today = today or date.today()
    result = RunResult(source.code)
    run_id = store.start_run(source.code)
    ctx = Context(source, client, store, files, settings, today, run_id, result)
    log.info("수집 시작", extra={"source": source.code, "recheck": recheck})
    try:
        if recheck:
            count = store.requeue_open_posts(source.code, today, settings.since_days)
            log.info("정정 확인 대상", extra={"source": source.code, "count": count})
        for board in source.boards:
            run_board(ctx, board, recheck=recheck)
    except BlockedError as error:
        result.status = "BLOCKED"
        ctx.warn(f"차단으로 이번 회차를 멈춰요: {error}")
    except Exception as error:  # noqa: BLE001 — 예상 못한 오류도 회차 기록은 남겨요
        result.status = "FAILED"
        ctx.warn(f"예상 못한 오류: {type(error).__name__}: {error}")
        log.exception("수집 실패", extra={"source": source.code})
    store.finish_run(run_id, result.status, result.new_count, result.warnings)
    log.info("수집 끝", extra={"source": source.code, "status": result.status, "new": result.new_count})
    return result


# ── 게시판 ─────────────────────────────────────────────────────
def run_board(ctx: Context, board: Board, *, recheck: bool = False) -> None:
    source, store, settings = ctx.source, ctx.store, ctx.settings
    state = store.board_state(source.code, board.key)
    queued_before = store.queued_posts(source.code, board.key, 1)
    cutoff = ctx.today - timedelta(days=settings.since_days)
    first_page_hash: str | None = None

    for page in range(1, settings.max_pages + 1):
        try:
            items = source.fetch_list(ctx.client, board, page)
        except ParseError as error:
            ctx.warn(f"[{board.name}] 목록 {page}페이지를 읽지 못해 이 게시판을 멈춰요 (구조 변경 의심): {error}")
            store.save_board_state(source.code, board.key, BoardState(state.last_list_hash, state.empty_runs + 1))
            return
        if page == 1:
            if not items:
                state.empty_runs += 1
                message = f"[{board.name}] 목록이 비어 있어요 ({state.empty_runs}회 연속)"
                ctx.warn(message + (" — 사이트 구조 변경 의심" if state.empty_runs >= settings.empty_alert else ""))
                store.save_board_state(source.code, board.key, state)
                return
            state.empty_runs = 0
            first_page_hash = list_hash([f"{i.post_key}|{i.title}|{i.posted_on}|{i.list_status or ''}" for i in items])
            if first_page_hash == state.last_list_hash and not queued_before and not recheck:
                log.info("목록 변화 없음", extra={"source": source.code, "board": board.key})
                store.save_board_state(source.code, board.key, state)
                return
        all_known = True
        for item in items:
            post = store.find_post(source.code, item.post_key)
            if post is not None:
                # 목록 한 줄도 새로 둬요: 상세 처리는 저장한 목록 값(본문을 목록 JSON에 싣는 출처, 목록 첨부·상태)을 쓰므로.
                # 단 그 글을 등록한 게시판의 줄일 때만: LH는 두 게시판(분양임대·마이홈)이 같은 글 번호를 써, 마이홈 줄로 덮으면
                # 상세 처리가 다른 게시판의 주소·값으로 공고를 열었어요(2026-11-10 재검토)
                same_board = post.board_key == board.key
                store.update_list_fields(post.id, item.list_status, item.deadline_on, item.to_json() if same_board else None)
                continue
            all_known = False
            register(ctx, item, cutoff)
        dates = [i.posted_on for i in items if i.posted_on]
        # 정정 확인 때는 「모두 아는 글」이어도 수집 기간 끝까지(최대 쪽수까지) 읽어요: 2페이지부터 있는 열린 공고의 목록 줄(목록에만 본문을 싣는
        # 출처의 본문)이 바뀌지 않아 정정을 놓쳤어요(2026-11-10 재검토). 평소 회차는 아는 글만 나오면 멈춰요
        if (all_known and not recheck) or (dates and min(dates) < cutoff) or not items:
            break

    relink_follow_ups(ctx, cutoff)
    for post in store.queued_posts(source.code, board.key, settings.detail_limit):
        process_safely(ctx, post)

    if not store.queued_posts(source.code, board.key, 1) and first_page_hash:
        state.last_list_hash = first_page_hash  # 밀린 글이 없을 때만 저장해서, 남은 글이 있으면 다음 회차에 다시 봐요
    store.save_board_state(source.code, board.key, state)


def register(ctx: Context, item: ListItem, cutoff: date) -> None:
    """목록에서 처음 본 글을 분류해서 저장해요. 열 글은 PENDING(처음 수집을 고르기 전이면 HELD), 안 열 글은 SKIPPED."""
    source, store = ctx.source, ctx.store
    kind = source.pre_classify(item) or cls.classify(item.title)
    status, parent, reason = SKIPPED, None, None
    if item.posted_on and item.posted_on < cutoff:
        reason = f"{ctx.settings.since_days}일 넘은 글"
    elif kind == cls.NOTICE:
        status = PENDING
    elif kind == cls.CORRECTION:
        status, parent = PENDING, find_correction_parent(store, source.code, item.title, item.posted_on)
    elif kind == cls.FOLLOW_UP:
        parent = find_followup_parent(store, source.code, item.title)
        if parent is not None:
            status = PENDING
        else:
            reason = ORPHAN_FOLLOW_UP  # 목록 읽기 뒤에 다시 찾아요(relink_follow_ups)
    else:
        reason = "모집공고가 아닌 글"
    if status == PENDING:
        status, reason = open_status(ctx, parent, item.posted_on)
    store.insert_post(
        PostRow(
            id=uuid7(),
            source_code=source.code,
            board_key=item.board,
            post_key=item.post_key,
            kind=kind,
            title=item.title,
            posted_on=item.posted_on,
            detail_url=item.detail_url,
            list_item=item.to_json(),
            status=status,
            last_error=reason,
            list_status=item.list_status,
            deadline_on=item.deadline_on,
            parent_post_id=parent.id if parent else None,
        )
    )


def open_status(ctx: Context, parent: PostRow | None, posted_on: date | None) -> tuple[str, str | None]:
    """열 글의 상태와 사유. 처음 수집 개수 제한: 고르기 전이면 HELD, 기준일보다 오래된 글이면 IGNORED (core/intake.py).
    쓰지 않는 원래 공고의 정정·후속 안내도 쓰지 않아요."""
    status = IGNORED if parent and parent.status == IGNORED else intake.open_status(ctx.store, intake.post_group(ctx.source.code), posted_on)
    return status, intake.IGNORED_REASON if status == IGNORED else None


def relink_follow_ups(ctx: Context, cutoff: date) -> int:
    """원공고를 찾지 못해 SKIPPED로 둔 최근 후속 안내를 다시 원공고에 이어요. 목록은 최신 글이 먼저라, 처음 수집·새 출처·원공고가 뒤쪽 목록에 있을 때
    후속 안내가 원공고보다 먼저 등록돼 영영 빠졌어요(2026-11-10 재검토: 다음 회차엔 이미 있는 글이라 다시 분류하지 않았음). 이은 수."""
    linked = 0
    for post in ctx.store.orphan_follow_ups(ctx.source.code, cutoff):
        parent = find_followup_parent(ctx.store, ctx.source.code, post.title)
        if parent is None:
            continue
        status, reason = open_status(ctx, parent, post.posted_on)
        ctx.store.link_follow_up(post.id, parent.id, status, reason)
        linked += 1
    return linked


def find_followup_parent(store: Store, source_code: str, title: str) -> PostRow | None:
    """후속 안내 제목 속 '(공고명, 공고일)'과 같은 모집공고."""
    ref = cls.title_ref(title)
    if ref is None:
        return None
    # 이름 비교는 괄호를 지우므로 괄호 안 구분(블록·단지)도 맞춰 봐요(정정공고와 같은 검사). 같은 날 올라온 「(A-2블록)」·「(A-3블록)」 공고가
    # 있으면 A-2블록 후속 안내가 A-3블록 공고에 붙었어요(2026-11-10 재검토)
    marks = cls.ref_qualifiers(title)
    return next(
        (
            p
            for p in store.notices_posted_on(source_code, ref.posted_on)
            if cls.same_notice(ref, p.title, p.posted_on) and cls.same_qualifiers(marks, cls.qualifiers(p.title))
        ),
        None,
    )


def find_correction_parent(store: Store, source_code: str, title: str, posted_on: date | None) -> PostRow | None:
    """정정공고 이름(정정 표시를 뺀 것)과 같은 가장 최근 모집공고. 정정공고보다 늦게 올라온 공고는 원래 공고가 아니에요
    (매달 같은 이름으로 올라오는 공고에서 다음 회차에 잘못 연결되지 않게. 같은 날은 허용, 게시일을 모르면 이름으로만)."""
    base = cls.correction_base(title)
    if not base:
        return None
    marks = cls.qualifiers(title)
    found = []
    for post in store.recent_notices(source_code):
        if posted_on and post.posted_on and post.posted_on > posted_on:
            continue
        own = cls.norm_name(post.title)
        # 이름 비교는 괄호를 지우므로 괄호 안 구분(블록·단지)도 맞춰 봐요.
        # 예전엔 「(A-2블록) 정정」이 같은 이름의 「(A-3블록)」 공고에 붙었어요(2026-11-10 코드 검토)
        if own and (own == base or own in base or base in own) and cls.same_qualifiers(marks, cls.qualifiers(post.title)):
            found.append(post)
    # 제목에 원래 공고일이 있으면(「…모집공고(2026.10.01) 당첨자 발표일 변경」) 그날 공고를 먼저, 없으면 가장 최근 것
    ref = cls.title_ref(title)
    dated = next((post for post in found if ref and post.posted_on == ref.posted_on), None)
    return dated or (found[0] if found else None)


# ── 글 하나 ────────────────────────────────────────────────────
def process_safely(ctx: Context, post: PostRow) -> None:
    try:
        if process_post(ctx, post):
            ctx.result.new_count += 1
    except BlockedError as error:
        # 출처 회차를 멈추되 이 글의 실패로 세요(3번까지). 세지 않으면 계속 403인 글 하나가 매 회차 먼저 열려
        # 출처 전체가 멈춰 있었어요(2026-11-10 코드 검토). FAILED는 PENDING 뒤라 다음 회차엔 다른 글이 먼저 열려요
        ctx.store.mark_failed(post.id, f"BlockedError: {error}")
        raise
    except FileUnavailable as error:
        # 이전 버전이 있어도 실패로 세요: 예전엔 DONE으로 두어 첨부가 계속 안 받아지면 본문 정정도 영영 새 버전이 되지 않았어요(2026-11-10 재검토).
        # 마지막 시도에선 받지 못한 첨부를 이전 버전 것으로 이어 써서 본문이 바뀌었을 때만 새 버전이 돼요(process_post)
        ctx.store.mark_failed(post.id, f"FileUnavailable: {error}")
        kept = " 이전 버전은 그대로 둬요." if post.latest_version else ""
        ctx.warn(f"[{post.post_key}] {post.title[:40]} — {error} 다음 회차에 다시 받아요.{kept}")
    except (ParseError, httpx.HTTPError) as error:
        ctx.store.mark_failed(post.id, f"{type(error).__name__}: {error}")
        ctx.warn(f"[{post.post_key}] {post.title[:40]} — 상세를 읽지 못했어요: {error}")
    except Exception as error:  # noqa: BLE001 — S3·DB 오류 등. 그 글만 FAILED로 두고 다음 글로 가요
        ctx.store.mark_failed(post.id, f"{type(error).__name__}: {error}")
        ctx.warn(f"[{post.post_key}] {post.title[:40]} — 저장하지 못했어요: {type(error).__name__}: {error}")
        log.exception("글 처리 실패", extra={"source": ctx.source.code, "post": post.post_key})


def process_post(ctx: Context, post: PostRow) -> bool:
    """상세 → 첨부 → 추출 → 버전 비교 → 저장·이벤트. 새 버전을 저장했으면 True."""
    source, client = ctx.source, ctx.client
    if post.kind == cls.CORRECTION and post.parent_post_id is None:
        # 목록은 최신 글이 먼저라, 같은 회차에 처음 본 원래 공고는 정정공고보다 늦게 등록돼요 (ih 검암역 푸르지오, 2026-10-21).
        # 상세는 목록 등록이 끝난 뒤에 열어서 이때는 원래 공고가 DB에 있어요
        parent = find_correction_parent(ctx.store, source.code, post.title, post.posted_on)
        if parent is not None and parent.id != post.id:
            ctx.store.set_parent(post.id, parent.id)
            post.parent_post_id = parent.id
    item = ListItem.from_json(post.list_item)
    detail = source.fetch_detail(client, item)
    candidates = detail.files or item.files
    referer = item.detail_url or item.referer

    saved: list[tuple[SavedFile, bytes | None]] = []  # (DB에 저장할 정보, S3에 올릴 원본. 이어 쓴 이전 첨부는 None)
    notice_name, notice_text = None, None
    keep_until = stored_until(post.title, post.deadline_on, post.posted_on, ctx.today)
    # 첨부 일시 오류면 마지막 시도 전까지 다음에 다시 받아요(FileUnavailable). 마지막 시도엔 이전 버전의 같은 첨부(주소, 없으면 이름이 같은 것)를
    # 이어 쓰고, 이전 것이 없으면 그 파일 없이 저장해요. 이전 버전이 있는 글을 그 파일 없이 저장하면 몇 시간 장애에도 열린 공고가 모두 공고문 없는
    # 버전이 되어 추출이 다시 돌아요. 본문이 그대로면 해시도 그대로라 새 버전이 되지 않아요
    retry_later = post.attempts + 1 < MAX_ATTEMPTS
    earlier = [] if retry_later or not post.latest_version else ctx.store.latest_files(post.id)

    def previous(file: FileRef) -> SavedFile | None:
        return next((f for f in earlier if f.download_url == file.url), None) or next((f for f in earlier if f.name == file.name), None)

    def fetch(file: FileRef) -> tuple[bytes | None, SavedFile | None]:
        """(받은 원본, 이어 쓴 이전 첨부) 중 하나. 둘 다 None이면 그 파일 없이."""
        before = previous(file)
        try:
            return download(ctx, file, referer, retry_later=retry_later or before is not None), None
        except FileUnavailable as error:
            if retry_later or before is None:
                raise
            ctx.warn(f"[{post.post_key}] {error} 이전 버전의 같은 첨부를 이어 써요")
            return None, dataclasses.replace(before, idx=file.index, name=file.name)

    notice_files = pick_notice_files(candidates, source.prefer_doc)
    if unclear_notice(candidates):
        ctx.warn(f"[{post.post_key}] 이름으로 공고문을 알 수 없어 첨부 순서로 골랐어요 ({notice_files[0].name})")
    for file in notice_files:  # 공고문: 첫 번째가 실패하면 두 번째
        data, kept = fetch(file)
        if kept is not None:
            saved.append((dataclasses.replace(kept, role="NOTICE_DOC"), None))
            if kept.text:
                notice_name, notice_text = file.name, kept.text
                break
            continue
        if data is None:
            continue
        text, status = extract_text(data, file.ext)
        saved.append((make_saved(file, "NOTICE_DOC", data, keep_until, status, text), data))
        if text:
            notice_name, notice_text = file.name, text
            break
        ctx.warn(f"[{post.post_key}] 공고문을 읽지 못했어요 ({file.name}): {status}")

    for file in pick_unit_lists(candidates):  # 주택목록: 엑셀 우선 최대 2개. 원본만 S3에 두고, 표 해석은 extraction이 해요
        data, kept = fetch(file)
        if kept is not None:
            saved.append((dataclasses.replace(kept, role="UNIT_LIST"), None))
            continue
        if data is None:
            continue
        saved.append((make_saved(file, "UNIT_LIST", data, keep_until, "원본만 저장", None), data))

    body = detail.body_text
    new_hash = content_hash(body, [f.file_hash for f, _ in saved])
    latest = ctx.store.latest_hash(post.id)
    if latest and latest[1] == new_hash:
        ctx.store.mark_done(post.id)  # 바뀐 게 없음 (새벽 정정 확인에서 대부분 여기로)
        return False
    version = (latest[0] if latest else 0) + 1

    for f, data in saved:  # 원본은 DB 트랜잭션 전에 S3에 올려요 (실패하면 그 글은 다음 회차에 다시 시도)
        if data is None:  # 이어 쓴 이전 첨부: 원본·보관 기한을 그대로 함께 써요(두 줄이 같은 날 지워져 남은 줄이 없는 원본을 가리키지 않게)
            continue
        f.s3_key = ctx.files.put(object_key(source.code, post.post_key, version, f.idx, f.name), data, content_type(ext_of(f.name)))

    meta = {**item.meta, **detail.meta}
    if item.list_status:
        meta.setdefault("목록상태", item.list_status)
    full_text = compose_full_text(source, post, item, detail, meta, notice_name, notice_text)
    long_text_key = None
    if len(full_text) > MAX_TEXT_CHARS:
        long_text_key = ctx.files.put(text_key(source.code, post.post_key, version), full_text.encode("utf-8"), content_type("txt"))

    event = build_collected_event(
        raw_post_id=post.id,
        version=version,
        source_code=source.code,
        provider=source.provider,
        kind=post.kind,
        title=post.title,
        posted_on=post.posted_on,
        detail_url=post.detail_url,
        parent_post_id=post.parent_post_id,
        full_text=full_text,
        text_key=long_text_key,
        files=[f.as_event_file() for f, _ in saved],
        region_code=detail.region_code,
        reprocess=False,
    )
    ctx.store.save_version(
        NewVersion(
            post=post,
            version=version,
            content_hash=new_hash,
            body_text=body,
            meta=meta,
            full_text=full_text,
            run_id=ctx.run_id,
            files=[f for f, _ in saved],
            event=event,
        )
    )
    log.info("새 버전 저장", extra={"source": source.code, "post": post.post_key, "version": version, "files": len(saved)})
    return True


def download(ctx: Context, file: FileRef, referer: str | None, *, retry_later: bool = False) -> bytes | None:
    """첨부 원본. 받지 않는 파일·없는 파일(4xx)은 None(그 파일 없이 저장). retry_later면 연결 오류·5xx 같은 일시 오류는
    FileUnavailable로 알려요: 그 파일만 빼고 새 버전을 만들면 해시가 바뀌어 추출·알림이 다시 돌고, 다음 회차에 파일이 오면
    또 바뀌었어요(2026-11-10 코드 검토)."""
    if file.personal:
        return None  # 명단 파일은 받지 않아요 (pick 단계에서 이미 빠지지만 한 번 더 막음)
    try:
        return ctx.client.download(file.url, referer=referer)
    except FileRejected as error:
        if retry_later and isinstance(error, FileNotReady):  # robots.txt를 잠시 못 받음·점검 화면: 일시 오류처럼 다음에 다시
            raise FileUnavailable(f"첨부를 잠시 받지 못했어요 ({file.name}): {error}.") from error
        ctx.warn(f"첨부를 받지 않았어요 ({file.name}): {error}")
    except httpx.HTTPError as error:
        if retry_later and transient(error):
            raise FileUnavailable(f"첨부를 잠시 받지 못했어요 ({file.name}): {error}.") from error
        ctx.warn(f"첨부를 받지 못했어요 ({file.name}): {error}")
    return None


def transient(error: httpx.HTTPError) -> bool:
    """다음 회차에 받아질 수 있는 오류: 연결·시간 초과, 5xx."""
    if isinstance(error, httpx.HTTPStatusError):
        return error.response is not None and error.response.status_code >= 500
    return isinstance(error, httpx.TransportError)


def make_saved(file: FileRef, role: str, data: bytes, keep_until: date, status: str | None, text: str | None) -> SavedFile:
    return SavedFile(
        idx=file.index,
        name=file.name,
        role=role,
        download_url=file.url,
        file_hash=sha256_hex(data),
        size_bytes=len(data),
        s3_key=None,
        stored_until=keep_until,
        text_status=status,
        text=text,
    )


def ext_of(name: str) -> str:
    return FileRef(name, "", 0).ext


def compose_full_text(source: Source, post: PostRow, item: ListItem, detail: Detail, meta: dict, notice_name: str | None, notice_text: str | None) -> str:
    """AI 추출(extraction)에 넘기는 전체 글자: 제목·게시 정보·항목·본문·공고문 순서.
    '_'로 시작하는 항목(예: LH의 '_raw' 원본 응답)은 원본 보관용이라 넣지 않아요."""
    lines = [
        f"제목: {post.title}",
        f"출처: {source.name} ({post.board_key})",
        f"게시일: {post.posted_on or detail.posted_on or ''}",
        f"주소: {post.detail_url or ''}",
    ]
    if meta:
        lines.append("[항목]")
        lines += [f"{key}: {value}" for key, value in meta.items() if value not in (None, "", [], {}) and not key.startswith("_")]
    lines += ["[본문]", detail.body_text or "(본문 없음)"]
    if notice_text:
        lines += [f"[공고문: {notice_name}]", notice_text]
    return "\n".join(lines)
