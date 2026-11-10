package kr.mujuthaek.api.notice.repository;

import java.sql.Array;
import java.sql.SQLException;
import java.time.Instant;
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import kr.mujuthaek.api.notice.domain.CompletedNotice;
import kr.mujuthaek.api.notice.domain.NoticeStatus;
import kr.mujuthaek.api.notice.domain.ReviewStatus;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

/**
 * 공고 쓰기: notices(목록 값·현재 버전), notice_versions(공개 버전), notice_posts(원본 글). 상세 내용은 JSON 글자로 주고받아요.
 */
@Repository
public class NoticeRepository {

  private final JdbcClient jdbc;

  /** 정책 판정 틀 한 건 (notice.policy_judgments). regionCodes는 시군구 5자리, 빈 목록은 전국. */
  public record PolicyJudgmentRow(
      UUID rawPolicyId,
      String field,
      int rawVersion,
      UUID sourceEventId,
      String title,
      LocalDate applyStart,
      LocalDate applyEnd,
      List<String> regionCodes,
      String frameJson,
      ReviewStatus reviewStatus,
      String detailUrl,
      boolean applyAlways,
      String infoJson) {}

  /** 저장된(공개 중인) 정책 판정 틀의 버전과 검수 상태. */
  public record PolicyJudgmentState(int version, ReviewStatus reviewStatus) {}

  /**
   * 정책 판정 틀을 저장해요. 더 높은 버전이 있거나, 같은 버전의 승인본(APPROVED)을 승인 아닌 결과로 덮으려 하면 바꾸지 않고 false (공고의
   * KEPT_APPROVED와 같은 규칙).
   */
  public boolean savePolicyJudgment(PolicyJudgmentRow row, Instant now) {
    return jdbc.sql(
                "insert into notice.policy_judgments (raw_policy_id, field, raw_version, source_event_id,"
                    + " title, apply_start, apply_end, region_codes, frame, review_status, detail_url,"
                    + " apply_always, info, created_at, updated_at) values (:id, :field, :version,"
                    + " :eventId, :title, :applyStart, :applyEnd, cast(:regions as text[]),"
                    + " cast(:frame as jsonb), :reviewStatus, :detailUrl, :applyAlways,"
                    + " cast(:info as jsonb), :now, :now)"
                    + " on conflict (raw_policy_id) do update set field = excluded.field,"
                    + " raw_version = excluded.raw_version, source_event_id = excluded.source_event_id,"
                    + " title = excluded.title, apply_start = excluded.apply_start,"
                    + " apply_end = excluded.apply_end, region_codes = excluded.region_codes,"
                    + " frame = excluded.frame, review_status = excluded.review_status,"
                    + " detail_url = excluded.detail_url, apply_always = excluded.apply_always,"
                    + " info = excluded.info,"
                    + " updated_at = excluded.updated_at"
                    + " where notice.policy_judgments.raw_version < excluded.raw_version"
                    + " or (notice.policy_judgments.raw_version = excluded.raw_version"
                    + " and (notice.policy_judgments.review_status <> 'APPROVED'"
                    + " or excluded.review_status = 'APPROVED'))")
            .param("id", row.rawPolicyId())
            .param("field", row.field())
            .param("version", row.rawVersion())
            .param("eventId", row.sourceEventId())
            .param("title", row.title())
            .param("applyStart", row.applyStart())
            .param("applyEnd", row.applyEnd())
            .param("regions", row.regionCodes().toArray(String[]::new))
            .param("frame", row.frameJson())
            .param("reviewStatus", row.reviewStatus().name())
            .param("detailUrl", row.detailUrl())
            .param("applyAlways", row.applyAlways())
            .param("info", row.infoJson())
            .param("now", now.atOffset(ZoneOffset.UTC))
            .update()
        == 1;
  }

  /** 저장된 정책 판정 틀에서 사용자가 보는 값 (새 버전과 비교해 정정 알림을 보내려고). */
  public record StoredPolicy(
      int version,
      String title,
      LocalDate applyStart,
      LocalDate applyEnd,
      boolean applyAlways,
      List<String> regionCodes,
      String frameJson,
      String detailUrl,
      String infoJson) {}

  /** 저장된 정책 판정 틀 (없으면 비어 있음). */
  public Optional<StoredPolicy> storedPolicy(UUID rawPolicyId) {
    return jdbc.sql(
            "select raw_version, title, apply_start, apply_end, apply_always, region_codes,"
                + " frame::text, detail_url, info::text from notice.policy_judgments"
                + " where raw_policy_id = :id")
        .param("id", rawPolicyId)
        .query(
            (rs, i) ->
                new StoredPolicy(
                    rs.getInt(1),
                    rs.getString(2),
                    rs.getObject(3, LocalDate.class),
                    rs.getObject(4, LocalDate.class),
                    rs.getBoolean(5),
                    List.of((String[]) rs.getArray(6).getArray()),
                    rs.getString(7),
                    rs.getString(8),
                    rs.getString(9)))
        .optional();
  }

  /** 저장된 정책 판정 틀의 버전과 검수 상태 (없으면 비어 있음). */
  public Optional<PolicyJudgmentState> policyJudgmentState(UUID rawPolicyId) {
    return jdbc.sql(
            "select raw_version, review_status from notice.policy_judgments where raw_policy_id = :id")
        .param("id", rawPolicyId)
        .query(
            (rs, i) -> new PolicyJudgmentState(rs.getInt(1), ReviewStatus.valueOf(rs.getString(2))))
        .optional();
  }

  public NoticeRepository(JdbcClient jdbc) {
    this.jdbc = jdbc;
  }

  /** 같은 원본 글을 처리하는 트랜잭션을 줄 세워요(트랜잭션이 끝나면 풀림). */
  public void lockRawPost(UUID rawPostId) {
    jdbc.sql("select pg_advisory_xact_lock(hashtextextended(cast(:id as text), 0))")
        .param("id", rawPostId)
        .query((rs, i) -> 1)
        .list();
  }

  /** 원본 글(원래 공고 또는 반영된 정정 공고)이 속한 공고. */
  public Optional<UUID> findNoticeIdByPost(UUID rawPostId) {
    return jdbc.sql("select notice_id from notice.notice_posts where raw_post_id = :id")
        .param("id", rawPostId)
        .query(UUID.class)
        .optional();
  }

  /**
   * 이 원본 글로 반영한 가장 높은 원본 버전과 그 검수 상태. 반영한 적이 없으면 빈 값. 공개 버전만 보면, 새 버전을 만들지 않은 결과(내용 같음·정정 유지) 뒤에 늦게
   * 온 옛 원본 버전이 새것으로 보여 반영돼요(v1 → 같은 내용 v3 → 다른 내용 v2). 처리 기록도 함께 봐요. 같은 원본 버전이면 승인본이 있는지가 중요해서(승인본을
   * 자동 결과로 덮지 않게) 승인을 앞에 둬요.
   */
  public Optional<SourceVersion> latestFromPost(UUID rawPostId) {
    return jdbc.sql(
            "select raw_version, review_status from ("
                + " select raw_version, review_status, created_at as at from notice.notice_versions"
                + " where raw_post_id = :rawPostId"
                + " union all select raw_version, review_status, received_at from notice.extraction_results"
                + " where raw_post_id = :rawPostId and outcome in ('NO_CHANGE', 'KEPT_BASE_SOURCE',"
                + " 'KEPT_CORRECTION', 'KEPT_APPROVED', 'APPROVAL_RECORDED')"
                + ") seen order by raw_version desc, (review_status = 'APPROVED') desc, at desc limit 1")
        .param("rawPostId", rawPostId)
        .query(
            (rs, i) ->
                new SourceVersion(
                    rs.getInt("raw_version"), ReviewStatus.valueOf(rs.getString("review_status"))))
        .optional();
  }

  /** 공고에 이은 정정 글 하나. linked: 원래 공고 글을 가리킴(supersedes_post_id 있음). */
  private record CorrectionPost(UUID rawPostId, LocalDate postedOn, boolean linked) {}

  /**
   * 기준 출처 줄기(base: 기준 출처의 최초 원공고 글)의 정정 글. base가 없으면(기준 출처를 정하기 전 공고) 모든 정정 글. 기준 출처가 아닌 출처의 정정은
   * 공고에 잇기만 하고 반영하지 않으니(KEPT_BASE_SOURCE) 세지 않아요. 예전엔 함께 세어, 합친 공고에서 다른 출처가 정정을 올리면 기준 출처의 새 버전이
   * 「정정 반영됨」으로 계속 막혀 공고가 옛 값으로 굳었어요(2026-11-10 코드 검토).
   */
  private List<CorrectionPost> corrections(UUID noticeId, UUID base) {
    List<CorrectionPost> all =
        jdbc.sql(
                "select raw_post_id, posted_on, supersedes_post_id is not null as linked"
                    + " from notice.notice_posts where notice_id = :id and kind = 'CORRECTION'")
            .param("id", noticeId)
            .query(
                (rs, i) ->
                    new CorrectionPost(
                        rs.getObject("raw_post_id", UUID.class),
                        rs.getObject("posted_on", LocalDate.class),
                        rs.getBoolean("linked")))
            .list();
    return base == null
        ? all
        : all.stream().filter(c -> base.equals(rootPostOf(c.rawPostId()))).toList();
  }

  /** 원래 공고를 가리키는 기준 출처의 정정 공고가 반영된 공고인지. base는 {@link #baseRoot} (없으면 null). */
  public boolean hasCorrection(UUID noticeId, UUID base) {
    return corrections(noticeId, base).stream().anyMatch(CorrectionPost::linked);
  }

  /**
   * 이 공고에 반영한 기준 출처의 정정 공고 중, 받은 글(rawPostId)이 아닌 것의 가장 늦은 게시일. 없거나 게시일을 모르면 빈 값. 늦게 도착한 더 이른 정정이
   * 최신 정정을 덮어쓰지 않게 비교해요. base는 {@link #baseRoot} (없으면 null).
   */
  public Optional<LocalDate> latestOtherCorrectionPostedOn(
      UUID noticeId, UUID rawPostId, UUID base) {
    return corrections(noticeId, base).stream()
        .filter(c -> !c.rawPostId().equals(rawPostId))
        .map(CorrectionPost::postedOn)
        .filter(java.util.Objects::nonNull)
        .max(java.util.Comparator.naturalOrder());
  }

  /** 원본 글을 공고에 이어요 (이미 있으면 게시일·시각만 갱신). postedOn은 원본 글 게시일 (모르면 null). */
  public void upsertPost(
      UUID rawPostId,
      UUID noticeId,
      String kind,
      UUID supersedesPostId,
      LocalDate postedOn,
      Instant now) {
    jdbc.sql(
            "insert into notice.notice_posts (raw_post_id, notice_id, kind, supersedes_post_id,"
                + " posted_on, original_notice_id, created_at, updated_at) values (:rawPostId,"
                + " :noticeId, :kind, :supersedes, :postedOn,"
                // 처음 속한 공고: 정정 공고는 원래 공고 글이 처음 속한 공고 (합친 뒤 들어온 정정도 되돌리면 원래 공고로)
                + " coalesce((select p.original_notice_id from notice.notice_posts p"
                + " where p.raw_post_id = :supersedes), :noticeId), :now, :now)"
                + " on conflict (raw_post_id) do update set"
                + " posted_on = coalesce(excluded.posted_on, notice.notice_posts.posted_on),"
                + " updated_at = :now")
        .param("rawPostId", rawPostId)
        .param("noticeId", noticeId)
        .param("kind", kind)
        .param("supersedes", supersedesPostId)
        .param("postedOn", postedOn)
        .param("now", utc(now))
        .update();
  }

  /** 공고의 현재 공개 버전을 잠그고 읽어요 (같은 공고의 버전 갱신을 줄 세워요). */
  public Optional<CurrentVersion> lockCurrent(UUID noticeId) {
    return jdbc.sql(
            "select n.id, n.current_version, n.status, v.raw_version, v.review_status, v.content_hash,"
                + " (v.payload -> 'notice')::text as snapshot, v.conditions::text as conditions,"
                + " v.held_items::text as held_items,"
                + " v.application_windows::text as application_windows,"
                + " case when jsonb_typeof(v.payload -> 'judgment') = 'object'"
                + " then (v.payload -> 'judgment')::text end as judgment"
                + " from notice.notices n join notice.notice_versions v"
                + " on v.notice_id = n.id and v.version = n.current_version"
                + " where n.id = :noticeId and n.merged_into is null for update of n")
        .param("noticeId", noticeId)
        .query(
            (rs, i) ->
                new CurrentVersion(
                    rs.getObject("id", UUID.class),
                    rs.getInt("current_version"),
                    NoticeStatus.valueOf(rs.getString("status")),
                    rs.getInt("raw_version"),
                    ReviewStatus.valueOf(rs.getString("review_status")),
                    rs.getString("content_hash"),
                    rs.getString("snapshot"),
                    rs.getString("conditions"),
                    rs.getString("held_items"),
                    rs.getString("application_windows"),
                    rs.getString("judgment")))
        .optional();
  }

  /**
   * 보충 발행할 공고 한 묶음 (ID 순서, after 다음부터). 합쳐진 공고는 빼고, includeClosed가 false면 마감 공고도 빼요.
   *
   * @param after 이전 묶음의 마지막 ID (처음이면 null)
   */
  public List<BackfillRow> findForBackfill(UUID after, int limit, boolean includeClosed) {
    return jdbc.sql(
            "select n.id, n.field, n.title, n.current_version, n.nationwide,"
                + " (v.payload -> 'notice')::text as detail,"
                + " array(select r.sigungu_code from notice.notice_regions r"
                + " where r.notice_id = n.id order by r.sigungu_code) as regions"
                + " from notice.notices n join notice.notice_versions v"
                + " on v.notice_id = n.id and v.version = n.current_version"
                + " where n.merged_into is null"
                + " and (cast(:after as uuid) is null or n.id > cast(:after as uuid))"
                + " and (:includeClosed or n.status <> 'CLOSED')"
                + " order by n.id limit :limit")
        .param("after", after)
        .param("includeClosed", includeClosed)
        .param("limit", limit)
        .query(
            (rs, i) ->
                new BackfillRow(
                    rs.getObject("id", UUID.class),
                    rs.getString("field"),
                    rs.getString("title"),
                    rs.getInt("current_version"),
                    strings(rs.getArray("regions")),
                    rs.getBoolean("nationwide"),
                    rs.getString("detail")))
        .list();
  }

  /** 공고 버전의 위치 목록 (상세 locations, JSON 글자). 없는 버전이면 빈 값. */
  public Optional<String> findLocations(UUID noticeId, int version) {
    return jdbc.sql(
            "select (payload -> 'notice' -> 'locations')::text from notice.notice_versions"
                + " where notice_id = :id and version = :version")
        .param("id", noticeId)
        .param("version", version)
        .query(String.class)
        .optional();
  }

  /** 새 공고를 공개해요. raw_post_id는 공고를 처음 만든 글로 두고(updateNotice는 바꾸지 않음), 정정은 notice_posts로 이어요. */
  public void insertNotice(UUID id, CompletedNotice n, int version, Listing listing, Instant now) {
    jdbc.sql(
            "insert into notice.notices (id, raw_post_id, field, title, provider, notice_type,"
                + " supply_type_text, region_code, apply_start, apply_end, posted_on, summary_text,"
                + " detail_url, current_version, current_raw_post_id, current_raw_version, reviewed,"
                + " status, next_status_check_at, needs_check, announced_on, base_root_post_id,"
                + " created_at, updated_at) values (:id, :rawPostId, :field, :title, :provider,"
                + " :noticeType, :supplyTypeText, :regionCode, :applyStart, :applyEnd, :postedOn,"
                + " :summary, :detailUrl, :version, :rawPostId, :rawVersion, :reviewed, :status,"
                + " :nextCheck, :needsCheck, :announcedOn, :rawPostId, :now, :now)")
        .params(listValues(id, n, version, listing))
        .param("now", utc(now))
        .update();
  }

  /** 공고의 목록 값과 현재 버전을 새 버전으로 바꿔요. */
  public void updateNotice(UUID id, CompletedNotice n, int version, Listing listing, Instant now) {
    jdbc.sql(
            "update notice.notices set field = :field, title = :title, provider = :provider,"
                + " notice_type = :noticeType, supply_type_text = :supplyTypeText,"
                + " region_code = :regionCode, apply_start = :applyStart, apply_end = :applyEnd,"
                + " posted_on = :postedOn, summary_text = :summary, detail_url = :detailUrl,"
                + " current_version = :version, current_raw_post_id = :rawPostId,"
                + " current_raw_version = :rawVersion, reviewed = :reviewed, status = :status,"
                + " next_status_check_at = :nextCheck, needs_check = :needsCheck,"
                + " announced_on = :announcedOn, updated_at = :now"
                + " where id = :id")
        .params(listValues(id, n, version, listing))
        .param("now", utc(now))
        .update();
  }

  /** 현재 공개 버전이 이 원본 글·원본 버전에서 왔으면 그 버전과 공고를 승인으로 올려요(내용이 같은 승인본, 새 버전 없음). 올렸으면 true. */
  public boolean markCurrentApproved(UUID noticeId, UUID rawPostId, int rawVersion, Instant now) {
    int updated =
        jdbc.sql(
                "update notice.notice_versions v set review_status = 'APPROVED'"
                    + " from notice.notices n where n.id = :id and v.notice_id = n.id"
                    + " and v.version = n.current_version and v.raw_post_id = :rawPostId"
                    + " and v.raw_version = :rawVersion")
            .param("id", noticeId)
            .param("rawPostId", rawPostId)
            .param("rawVersion", rawVersion)
            .update();
    if (updated > 0) {
      jdbc.sql("update notice.notices set reviewed = true, updated_at = :now where id = :id")
          .param("id", noticeId)
          .param("now", utc(now))
          .update();
    }
    return updated > 0;
  }

  /** 지역 색인을 바꿔요. regions는 지역 5자리 → 대상 지역 전체(AREA)인지. nationwide면 전국 대상이라 어느 지역 검색에도 나와요. */
  public void replaceRegions(UUID noticeId, Map<String, Boolean> regions, boolean nationwide) {
    jdbc.sql("update notice.notices set nationwide = :nationwide where id = :id")
        .param("id", noticeId)
        .param("nationwide", nationwide)
        .update();
    jdbc.sql("delete from notice.notice_regions where notice_id = :id")
        .param("id", noticeId)
        .update();
    for (Map.Entry<String, Boolean> region : regions.entrySet()) {
      jdbc.sql(
              "insert into notice.notice_regions (notice_id, sigungu_code, whole)"
                  + " values (:id, :code, :whole)")
          .param("id", noticeId)
          .param("code", region.getKey())
          .param("whole", region.getValue())
          .update();
    }
  }

  /** 다시 계산할 시각이 지난 공고를 잠그고 읽어요. 다른 서버가 이미 잡은 공고는 건너뛰어요(skip locked). 일정은 현재 버전의 원문 일정(상세)에서 읽어요. */
  public List<StatusCheckRow> lockDueForStatusCheck(Instant now, int limit) {
    return jdbc.sql(
            "select n.id, n.field, n.status, (v.payload -> 'notice')::text as detail,"
                + " v.review_status"
                + " from notice.notices n join notice.notice_versions v"
                + " on v.notice_id = n.id and v.version = n.current_version"
                + " where n.next_status_check_at <= :now and n.merged_into is null"
                + " order by n.next_status_check_at limit :limit"
                + " for update of n skip locked")
        .param("now", utc(now))
        .param("limit", limit)
        .query(
            (rs, i) ->
                new StatusCheckRow(
                    rs.getObject("id", UUID.class),
                    rs.getString("field"),
                    NoticeStatus.valueOf(rs.getString("status")),
                    rs.getString("detail"),
                    ReviewStatus.valueOf(rs.getString("review_status"))))
        .list();
  }

  public void updateStatus(UUID noticeId, NoticeStatus status, Instant nextCheckAt, Instant now) {
    jdbc.sql(
            "update notice.notices set status = :status, next_status_check_at = :nextCheck,"
                + " updated_at = :now where id = :id")
        .param("id", noticeId)
        .param("status", status.name())
        .param("nextCheck", nextCheckAt == null ? null : utc(nextCheckAt))
        .param("now", utc(now))
        .update();
  }

  public void insertVersion(VersionRow row, Instant now) {
    jdbc.sql(
            "insert into notice.notice_versions (notice_id, version, raw_post_id, raw_version,"
                + " source_event_id, review_status, payload, conditions, held_items,"
                + " application_windows, content_hash, changed_fields, created_at) values"
                + " (:noticeId, :version, :rawPostId, :rawVersion, :eventId, :reviewStatus,"
                + " cast(:payload as jsonb), cast(:conditions as jsonb), cast(:heldItems as jsonb),"
                + " cast(:windows as jsonb), :contentHash, cast(:changedFields as jsonb), :now)")
        .param("noticeId", row.noticeId())
        .param("version", row.version())
        .param("rawPostId", row.rawPostId())
        .param("rawVersion", row.rawVersion())
        .param("eventId", row.sourceEventId())
        .param("reviewStatus", row.reviewStatus().name())
        .param("payload", row.payloadJson())
        .param("conditions", row.conditionsJson())
        .param("heldItems", row.heldItemsJson())
        .param("windows", row.applicationWindowsJson())
        .param("contentHash", row.contentHash())
        .param("changedFields", row.changedFieldsJson())
        .param("now", utc(now))
        .update();
  }

  // ---------- 같은 공고 합치기 ----------

  /**
   * 같은 공고일 수 있는 새 공고 공개를 줄 세워요(분야·공급기관 단위, 트랜잭션이 끝나면 풀림). 원본 글 잠금만으로는 출처가 다른 같은 공고가 동시에 오면 둘 다
   * 공개돼요. 잠금을 얻은 뒤 후보를 다시 조회하면 먼저 공개된 공고가 보여요.
   */
  public void lockIdentity(String field, String publisherKey) {
    jdbc.sql("select pg_advisory_xact_lock(hashtextextended(cast(:key as text), 1))")
        .param("key", "notice-identity:" + field + ":" + publisherKey)
        .query((rs, i) -> 1)
        .list();
  }

  /**
   * 두 공고의 모든 원본 글을 반영과 같은 순서로 잠가요(합치기용). 반영은 원래 글 → 정정 글 순서로 원본 글을 잠그므로, 원래 공고(NOTICE) 글을 먼저, 정정 글을
   * 나중에(각각 ID 순서) 잠가 서로 엇갈려 교착되지 않게 해요. 잠금을 잡으면 그 글들의 반영이 끝날 때까지 기다리고, 합치는 동안 새 반영이 시작되지 않아요.
   */
  public void lockPostsOf(UUID first, UUID second) {
    List<UUID> rawPosts =
        jdbc.sql(
                "select raw_post_id from notice.notice_posts where notice_id in (:first, :second)"
                    + " order by case when kind = 'NOTICE' then 0 else 1 end, raw_post_id")
            .param("first", first)
            .param("second", second)
            .query(UUID.class)
            .list();
    for (UUID rawPost : rawPosts) {
      lockRawPost(rawPost);
    }
  }

  /** 공고 분야 (공고 이벤트에 실어요). 없는 공고면 빈 값. */
  public Optional<String> fieldOf(UUID noticeId) {
    return jdbc.sql("select field from notice.notices where id = :id")
        .param("id", noticeId)
        .query(String.class)
        .optional();
  }

  /** 합쳐진 공고면 합친 공고 ID(합침이 이어져도 마지막 공고), 아니면 그대로. */
  public UUID resolveMerged(UUID noticeId) {
    return jdbc.sql("select coalesce(merged_into, id) from notice.notices where id = :id")
        .param("id", noticeId)
        .query(UUID.class)
        .optional()
        .orElse(noticeId);
  }

  /**
   * 원본 글이 속한 출처 줄기의 최초 원공고 글. 정정을 다시 정정한 글(C2 → C1 → N)이면 N이에요(바로 앞 글 C1을 줄기로 쓰면 「기준 출처 아님」으로 빠져요).
   * 모르는 글이면 그 글 자신.
   */
  public UUID rootPostOf(UUID rawPostId) {
    return jdbc.sql(
            "with recursive chain(id, depth) as (select cast(:id as uuid), 0"
                + " union all select p.supersedes_post_id, c.depth + 1 from notice.notice_posts p"
                + " join chain c on p.raw_post_id = c.id"
                + " where p.kind = 'CORRECTION' and p.supersedes_post_id is not null and c.depth < 50)"
                + " select id from chain order by depth desc limit 1")
        .param("id", rawPostId)
        .query(UUID.class)
        .single();
  }

  /** 원본 글이 처음 속한 공고 (없으면 빈 값). 후속 안내의 처음 공고를 정할 때 써요. */
  public Optional<UUID> originalNoticeOf(UUID rawPostId) {
    return jdbc.sql("select original_notice_id from notice.notice_posts where raw_post_id = :id")
        .param("id", rawPostId)
        .query(UUID.class)
        .optional();
  }

  /**
   * 출처(원래 공고 글)의 마지막 반영 결과를 기록해요. 처음이면 지금 공고를 처음 공고로 남겨요. hasPdf·게시일은 마지막 결과 기준이에요(게시일은 모르면 이전 값
   * 유지).
   */
  public void upsertSourceHead(
      UUID root, UUID noticeId, UUID eventId, boolean hasPdf, LocalDate postedOn, Instant now) {
    jdbc.sql(
            "insert into notice.notice_source_heads (root_post_id, notice_id, original_notice_id,"
                + " latest_event_id, has_pdf, posted_on, first_seen_at, updated_at) values (:root,"
                + " :noticeId, :noticeId, :eventId, :hasPdf, :postedOn, :now, :now)"
                + " on conflict (root_post_id) do update set latest_event_id = excluded.latest_event_id,"
                + " has_pdf = excluded.has_pdf,"
                + " posted_on = coalesce(excluded.posted_on, notice.notice_source_heads.posted_on),"
                + " updated_at = excluded.updated_at")
        .param("root", root)
        .param("noticeId", noticeId)
        .param("eventId", eventId)
        .param("hasPdf", hasPdf)
        .param("postedOn", postedOn)
        .param("now", utc(now))
        .update();
  }

  /** 공고에 속한 출처들. */
  public List<SourceHead> findSourceHeads(UUID noticeId) {
    return jdbc.sql(
            "select root_post_id, latest_event_id, has_pdf, posted_on, first_seen_at"
                + " from notice.notice_source_heads where notice_id = :id")
        .param("id", noticeId)
        .query(
            (rs, i) ->
                new SourceHead(
                    rs.getObject("root_post_id", UUID.class),
                    rs.getObject("latest_event_id", UUID.class),
                    rs.getBoolean("has_pdf"),
                    rs.getObject("posted_on", LocalDate.class),
                    rs.getObject("first_seen_at", OffsetDateTime.class).toInstant()))
        .list();
  }

  /** 공고의 기준 출처(원래 공고 글). 정해지지 않았으면 빈 값. */
  public Optional<UUID> baseRoot(UUID noticeId) {
    return jdbc.sql("select base_root_post_id from notice.notices where id = :id")
        .param("id", noticeId)
        .query((rs, i) -> Optional.ofNullable(rs.getObject("base_root_post_id", UUID.class)))
        .optional()
        .flatMap(o -> o);
  }

  public void setBaseRoot(UUID noticeId, UUID root, Instant now) {
    jdbc.sql(
            "update notice.notices set base_root_post_id = :root, updated_at = :now where id = :id")
        .param("id", noticeId)
        .param("root", root)
        .param("now", utc(now))
        .update();
  }

  /** 수신 기록에 보관한 결과 payload (기준 출처를 바꾸거나 되돌릴 때 다시 적용). */
  public Optional<String> storedPayload(UUID eventId) {
    return jdbc.sql("select payload::text from notice.extraction_results where event_id = :id")
        .param("id", eventId)
        .query(String.class)
        .optional();
  }

  /** 합쳐진 공고가 합쳐진 대상 (합쳐지지 않았으면 빈 값). */
  public Optional<UUID> mergedInto(UUID noticeId) {
    return jdbc.sql("select merged_into from notice.notices where id = :id")
        .param("id", noticeId)
        .query((rs, i) -> Optional.ofNullable(rs.getObject("merged_into", UUID.class)))
        .optional()
        .flatMap(o -> o);
  }

  /**
   * 같은 분야이고 공고일이 days일 안인 다른 공고 (합쳐지지 않은 것만, 먼저 공개된 순서). 분야가 다른 공고는 합칠 수 없어 후보로도 찾지 않아요. 기관·단지 이름은
   * 현재 공개 버전의 상세에서 가져와요(payload의 provider는 수집 출처라 출처마다 달라요).
   */
  public List<Peer> findIdentityPeers(
      String field, LocalDate announcedOn, int days, UUID excludeId) {
    return identities(
        " and n.field = :field and n.announced_on between :from and :to and n.id <> :excludeId",
        Map.of(
            "field",
            field,
            "from",
            announcedOn.minusDays(days),
            "to",
            announcedOn.plusDays(days),
            "excludeId",
            excludeId));
  }

  /** 합쳐지지 않은 공고 전체의 같은 공고 판별 정보 (공개된 순서). 이미 공개된 공고끼리 다시 훑어 합칠 때 써요. */
  public List<Peer> findOpenIdentities() {
    return identities("", Map.of());
  }

  private List<Peer> identities(String condition, Map<String, Object> params) {
    return jdbc.sql(
            "select n.id, n.field, n.title, n.announced_on, n.supply_type_text,"
                + " v.payload -> 'notice' -> 'notice' ->> 'publisher' as publisher,"
                + " array(select r.sigungu_code from notice.notice_regions r"
                + " where r.notice_id = n.id) as regions,"
                + " array(select distinct coalesce(l->>'complexName', l->>'buildingName')"
                + " from jsonb_array_elements(v.payload->'notice'->'locations') l"
                + " where coalesce(l->>'complexName', l->>'buildingName') is not null) as names"
                + " from notice.notices n join notice.notice_versions v"
                + " on v.notice_id = n.id and v.version = n.current_version"
                // 기관은 정식 명칭·약칭 표기가 달라 DuplicateRule에서 비교해요
                + " where n.announced_on is not null and n.merged_into is null"
                + " and v.payload -> 'notice' -> 'notice' ->> 'publisher' is not null"
                + condition
                + " order by n.created_at, n.id")
        .params(params)
        .query(
            (rs, i) ->
                new Peer(
                    rs.getObject("id", UUID.class),
                    rs.getString("field"),
                    rs.getString("publisher"),
                    rs.getString("title"),
                    strings(rs.getArray("regions")),
                    rs.getObject("announced_on", LocalDate.class),
                    rs.getString("supply_type_text"),
                    strings(rs.getArray("names"))))
        .list();
  }

  public void insertDuplicateCandidate(
      UUID noticeId, UUID candidateOf, String reason, Instant now) {
    jdbc.sql(
            "insert into notice.notice_duplicate_candidates (notice_id, candidate_of, reason,"
                + " status, created_at) values (:noticeId, :candidateOf, :reason, 'PENDING', :now)"
                + " on conflict do nothing")
        .param("noticeId", noticeId)
        .param("candidateOf", candidateOf)
        .param("reason", reason)
        .param("now", utc(now))
        .update();
  }

  public List<DuplicateCandidate> findPendingCandidates() {
    return jdbc.sql(
            "select c.notice_id, a.title as notice_title, c.candidate_of,"
                + " b.title as candidate_title, c.reason, c.created_at"
                + " from notice.notice_duplicate_candidates c"
                + " join notice.notices a on a.id = c.notice_id"
                + " join notice.notices b on b.id = c.candidate_of"
                + " where c.status = 'PENDING' order by c.created_at")
        .query(
            (rs, i) ->
                new DuplicateCandidate(
                    rs.getObject("notice_id", UUID.class),
                    rs.getString("notice_title"),
                    rs.getObject("candidate_of", UUID.class),
                    rs.getString("candidate_title"),
                    rs.getString("reason"),
                    rs.getObject("created_at", OffsetDateTime.class).toInstant()))
        .list();
  }

  /**
   * 두 공고를 같은 공고로 보지 않기로 한 기록(UNMERGED: 합친 뒤 되돌림, REJECTED: 같은 공고 아님)을 남겨요. 후보 기록이 없거나 이미
   * 합쳐짐(MERGED)이어도 남겨, 다시 훑기·자동 합치기가 이 쌍을 다시 합치지 않게 해요.
   */
  public void markNotSame(UUID from, UUID into, String status, Instant now) {
    jdbc.sql(
            "update notice.notice_duplicate_candidates set status = :status, decided_at = :now"
                + " where (notice_id = :a and candidate_of = :b) or (notice_id = :b and candidate_of = :a)")
        .param("a", from)
        .param("b", into)
        .param("status", status)
        .param("now", utc(now))
        .update();
    jdbc.sql(
            "insert into notice.notice_duplicate_candidates (notice_id, candidate_of, reason,"
                + " status, created_at, decided_at) select :a, :b, :reason, :status, :now, :now"
                + " where not exists (select 1 from notice.notice_duplicate_candidates"
                + " where (notice_id = :a and candidate_of = :b) or (notice_id = :b and candidate_of = :a))")
        .param("a", from)
        .param("b", into)
        .param("reason", status)
        .param("status", status)
        .param("now", utc(now))
        .update();
  }

  /** 두 공고를 같은 공고로 보지 않기로 했는지(되돌림·거절, 어느 쪽 방향이든). */
  public boolean markedNotSame(UUID a, UUID b) {
    return jdbc.sql(
            "select exists (select 1 from notice.notice_duplicate_candidates"
                + " where status in ('UNMERGED', 'REJECTED')"
                + " and ((notice_id = :a and candidate_of = :b) or (notice_id = :b and candidate_of = :a)))")
        .param("a", a)
        .param("b", b)
        .query(Boolean.class)
        .single();
  }

  /** 두 공고 사이의 대기 중인 후보를 정리해요 (어느 쪽 방향이든). */
  public int decideCandidates(UUID a, UUID b, String status, Instant now) {
    return jdbc.sql(
            "update notice.notice_duplicate_candidates set status = :status, decided_at = :now"
                + " where status = 'PENDING' and ((notice_id = :a and candidate_of = :b)"
                + " or (notice_id = :b and candidate_of = :a))")
        .param("a", a)
        .param("b", b)
        .param("status", status)
        .param("now", utc(now))
        .update();
  }

  /** 합치기 전에 공고를 잠그고 상태를 읽어요. */
  public Optional<MergeState> lockForMerge(UUID noticeId) {
    return jdbc.sql("select id, field, merged_into from notice.notices where id = :id for update")
        .param("id", noticeId)
        .query(
            (rs, i) ->
                new MergeState(
                    rs.getObject("id", UUID.class),
                    rs.getString("field"),
                    rs.getObject("merged_into", UUID.class)))
        .optional();
  }

  /** from 공고를 into 공고에 합쳐요: 원본 글·출처를 옮기고, from은 목록·재계산에서 빠져요. */
  public void mergeInto(UUID from, UUID into, Instant now) {
    for (String table : List.of("notice_posts", "notice_source_heads")) {
      jdbc.sql("update notice." + table + " set notice_id = :into where notice_id = :from")
          .param("from", from)
          .param("into", into)
          .update();
    }
    jdbc.sql(
            "update notice.notices set merged_into = :into, next_status_check_at = null,"
                + " updated_at = :now where id = :from")
        .param("from", from)
        .param("into", into)
        .param("now", utc(now))
        .update();
    // 예전에 from으로 합쳐진 공고도 into를 가리키게 해요 (합침이 이어져도 한 번에 찾게)
    jdbc.sql("update notice.notices set merged_into = :into where merged_into = :from")
        .param("from", from)
        .param("into", into)
        .update();
  }

  /**
   * 합치기를 되돌려요: from 공고를 다시 살리고, from에 처음 속했던 원본 글·출처·후속 안내를 from으로 돌려놓아요. into에 다른 공고가 합쳐진 기록은
   * 그대로예요.
   */
  public void unmerge(UUID from, UUID into, Instant now) {
    jdbc.sql(
            "update notice.notices set merged_into = null, next_status_check_at = :now,"
                + " updated_at = :now where id = :from")
        .param("from", from)
        .param("now", utc(now))
        .update();
    for (String table : List.of("notice_posts", "notice_source_heads", "notice_follow_ups")) {
      jdbc.sql(
              "update notice."
                  + table
                  + " set notice_id = :from where notice_id = :into and original_notice_id = :from")
          .param("from", from)
          .param("into", into)
          .update();
    }
  }

  private static List<String> strings(Array array) throws SQLException {
    if (array == null) {
      return List.of();
    }
    List<String> values = new ArrayList<>(List.of((String[]) array.getArray()));
    array.free();
    return values;
  }

  private static Map<String, Object> listValues(
      UUID id, CompletedNotice n, int version, Listing listing) {
    Map<String, Object> params = new LinkedHashMap<>();
    params.put("id", id);
    params.put("rawPostId", n.rawPostId());
    params.put("field", n.field());
    params.put("title", n.title());
    params.put("provider", n.provider());
    params.put("noticeType", n.noticeType() == null ? null : n.noticeType().name());
    params.put("supplyTypeText", n.supplyTypeText());
    params.put("regionCode", n.regionCode());
    params.put("applyStart", n.applyStart());
    params.put("applyEnd", n.applyEnd());
    params.put("postedOn", n.postedOn());
    params.put("summary", n.summary());
    params.put("detailUrl", n.detailUrl());
    params.put("version", version);
    params.put("rawVersion", n.rawVersion());
    params.put("reviewed", n.approved());
    params.put("status", listing.status().name());
    params.put("nextCheck", listing.nextCheckAt() == null ? null : utc(listing.nextCheckAt()));
    params.put("needsCheck", listing.needsCheck());
    params.put("announcedOn", listing.announcedOn());
    return params;
  }

  private static OffsetDateTime utc(Instant instant) {
    return instant.atOffset(ZoneOffset.UTC);
  }

  /**
   * 버전과 함께 바뀌는 목록 값.
   *
   * @param nextCheckAt 접수 상태를 다시 계산할 시각 (없으면 null)
   * @param needsCheck 원문 확인 전까지 보류한 항목이 있는지
   * @param announcedOn 공고일 (같은 공고 후보 찾기용, 보류했으면 null)
   */
  public record Listing(
      NoticeStatus status, Instant nextCheckAt, boolean needsCheck, LocalDate announcedOn) {}

  /** 접수 상태를 다시 계산할 공고. detailJson은 현재 버전의 상세(원문 일정·보류 항목). */
  public record StatusCheckRow(
      UUID noticeId,
      String field,
      NoticeStatus status,
      String detailJson,
      ReviewStatus reviewStatus) {}

  /** 공고의 현재 공개 버전 (새 결과와 비교할 때 써요). */
  public record CurrentVersion(
      UUID noticeId,
      int version,
      NoticeStatus status,
      int rawVersion,
      ReviewStatus reviewStatus,
      String contentHash,
      String snapshotJson,
      String conditionsJson,
      String heldItemsJson,
      String applicationWindowsJson,
      String judgmentJson) {}

  /** 공고에 속한 출처 하나 (기준 출처 고르기·되돌리기용). */
  public record SourceHead(
      UUID root, UUID latestEventId, boolean hasPdf, LocalDate postedOn, Instant firstSeenAt) {}

  /** 같은 공고 후보를 찾을 때 비교하는 다른 공고. */
  public record Peer(
      UUID noticeId,
      String field,
      String publisher,
      String title,
      List<String> sigunguCodes,
      LocalDate announcedOn,
      String supplyType,
      List<String> complexNames) {}

  /** 대기 중인 같은 공고 후보. */
  public record DuplicateCandidate(
      UUID noticeId,
      String noticeTitle,
      UUID candidateOf,
      String candidateTitle,
      String reason,
      Instant createdAt) {}

  /** 보충 발행할 공고. detailJson은 현재 버전의 상세. */
  public record BackfillRow(
      UUID noticeId,
      String field,
      String title,
      int version,
      List<String> sigunguCodes,
      boolean nationwide,
      String detailJson) {}

  /** 합치기 전 공고 상태. */
  public record MergeState(UUID noticeId, String field, UUID mergedInto) {}

  /** 한 원본 글에서 마지막으로 반영한 버전. */
  public record SourceVersion(int rawVersion, ReviewStatus reviewStatus) {}

  /** notice_versions 한 줄. JSON 칸은 글자로. */
  public record VersionRow(
      UUID noticeId,
      int version,
      UUID rawPostId,
      int rawVersion,
      UUID sourceEventId,
      ReviewStatus reviewStatus,
      String payloadJson,
      String conditionsJson,
      String heldItemsJson,
      String applicationWindowsJson,
      String contentHash,
      String changedFieldsJson) {}
}
