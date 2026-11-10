package kr.mujuthaek.api.notice.repository;

import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

/**
 * 공고·창업지원 사업·혜택 정책 제보 (notice.notice_reports). 대상은 공고(notice_id)·사업(raw_policy_id)·혜택
 * 정책(benefit_policy_id) 중 하나예요.
 */
@Repository
public class NoticeReportRepository {

  private static final String COLUMNS =
      "r.id, r.notice_id, r.raw_policy_id, r.benefit_policy_id, coalesce(n.title, p.title,"
          + " r.target_title) as title, r.reporter_id,"
          + " r.field, r.current_value, r.reported_value,"
          + " r.note, r.screen, r.status, r.result, r.reply, r.handled_by, r.created_at,"
          + " r.started_at, r.handled_at, r.review_job_id,"
          // 같은 대상·같은 칸의 열린 제보 수. 대상 종류마다 = 로 비교해 부분 인덱스(대상, field) where status <> 'DONE'을 써요
          // (한 제보는 대상이 하나뿐이라 is not distinct from 세 개와 결과가 같아요, 2026-10-30 부하 시험: 13.7ms → 2.5ms)
          + " case when r.notice_id is not null then (select count(*) from notice.notice_reports g"
          + " where g.notice_id = r.notice_id and g.field = r.field and g.status <> 'DONE')"
          + " when r.raw_policy_id is not null then (select count(*) from notice.notice_reports g"
          + " where g.raw_policy_id = r.raw_policy_id and g.field = r.field and g.status <> 'DONE')"
          + " when r.benefit_policy_id is not null then (select count(*) from notice.notice_reports g"
          + " where g.benefit_policy_id = r.benefit_policy_id and g.field = r.field and g.status <> 'DONE')"
          // 일반 제보(대상 없음)는 묶지 않아요: 같은 종류라도 내용이 매번 달라요
          + " else 0 end as open_in_group";

  private final JdbcClient jdbc;

  public NoticeReportRepository(JdbcClient jdbc) {
    this.jdbc = jdbc;
  }

  /** 공개된 공고의 제목 (없거나 숨김·공개 전이면 비어 있음). */
  public Optional<String> publishedTitle(UUID noticeId) {
    return jdbc.sql(
            "select title from notice.notices where id = :id and current_version > 0 and not"
                + " hidden")
        .param("id", noticeId)
        .query(String.class)
        .optional();
  }

  /** 판정 틀이 있는 창업지원 사업·사업공간 모집의 이름 (없으면 비어 있음). */
  public Optional<String> programTitle(UUID rawPolicyId) {
    return jdbc.sql(
            "select title from notice.policy_judgments where raw_policy_id = :id and field in"
                + " ('STARTUP_SUPPORT', 'SPACE_RECRUITMENT')")
        .param("id", rawPolicyId)
        .query(String.class)
        .optional();
  }

  /** 그 회원이 since 뒤에 낸 제보 수. */
  public int countSince(UUID reporterId, Instant since) {
    return jdbc.sql(
            "select count(*) from notice.notice_reports where reporter_id = :r and created_at >="
                + " :since")
        .param("r", reporterId)
        .param("since", OffsetDateTime.ofInstant(since, ZoneOffset.UTC))
        .query(Integer.class)
        .single();
  }

  /** 넣어요. 같은 회원·공고·칸의 처리 전 제보가 있으면 넣지 않고 false. */
  public boolean insert(Row row) {
    return jdbc.sql(
                "insert into notice.notice_reports (id, notice_id, raw_policy_id,"
                    + " benefit_policy_id, target_title, reporter_id, field, current_value,"
                    + " reported_value, note, screen, created_at) values (:id, :notice, :program,"
                    + " :benefit, :title, :reporter, :field, :current, :reported, :note, :screen,"
                    + " :now) on conflict do nothing")
            .param("id", row.id())
            .param("notice", row.noticeId())
            .param("program", row.rawPolicyId())
            .param("benefit", row.benefitPolicyId())
            .param("title", row.targetTitle())
            .param("reporter", row.reporterId())
            .param("field", row.field())
            .param("current", row.currentValue())
            .param("reported", row.reportedValue())
            .param("note", row.note())
            .param("screen", row.screen())
            .param("now", OffsetDateTime.ofInstant(row.createdAt(), ZoneOffset.UTC))
            .update()
        == 1;
  }

  /** 최근 처리 끝낸 제보 (관리자 「처리 기록」, 처리한 시각 최근 순). */
  public List<Report> handledSince(java.time.Instant since, int limit) {
    return jdbc.sql(
            "select "
                + COLUMNS
                + " from notice.notice_reports r left join notice.notices n on n.id = r.notice_id left join notice.policy_judgments p on p.raw_policy_id = r.raw_policy_id"
                + " where r.status = 'DONE' and r.handled_at >= :since"
                + " order by r.handled_at desc limit :limit")
        .param("since", OffsetDateTime.ofInstant(since, ZoneOffset.UTC))
        .param("limit", limit)
        .query(NoticeReportRepository::report)
        .list();
  }

  /** 한 회원이 보낸 제보 (최근 것부터) */
  public List<Report> byReporter(UUID reporterId, int limit) {
    return jdbc.sql(
            "select "
                + COLUMNS
                + " from notice.notice_reports r left join notice.notices n on n.id = r.notice_id left join notice.policy_judgments p on p.raw_policy_id = r.raw_policy_id"
                + " where r.reporter_id = :r order by r.created_at desc limit :limit")
        .param("r", reporterId)
        .param("limit", limit)
        .query(NoticeReportRepository::report)
        .list();
  }

  /**
   * 관리자 제보 대기열 한 쪽: 그 상태의 제보를 최신순으로 limit건. before(들어온 시각·ID)가 있으면 그 건 다음(더 오래된 것)부터. (status,
   * created_at desc) 인덱스를 써요.
   */
  public List<Report> page(String status, OffsetDateTime beforeAt, UUID beforeId, int limit) {
    return jdbc.sql(
            "select "
                + COLUMNS
                + " from notice.notice_reports r left join notice.notices n on n.id = r.notice_id left join notice.policy_judgments p on p.raw_policy_id = r.raw_policy_id"
                + " where r.status = :status and (cast(:beforeAt as timestamptz) is null"
                + " or (r.created_at, r.id) < (cast(:beforeAt as timestamptz), cast(:beforeId as uuid)))"
                + " order by r.created_at desc, r.id desc limit :limit")
        .param("status", status)
        .param("beforeAt", beforeAt)
        .param("beforeId", beforeId)
        .param("limit", limit)
        .query(NoticeReportRepository::report)
        .list();
  }

  public List<Report> list(String status, int limit) {
    return jdbc.sql(
            "select "
                + COLUMNS
                + " from notice.notice_reports r left join notice.notices n on n.id = r.notice_id left join notice.policy_judgments p on p.raw_policy_id = r.raw_policy_id"
                + " where (cast(:status as text) is null or r.status = :status)"
                + " order by r.created_at desc limit :limit")
        .param("status", status)
        .param("limit", limit)
        .query(NoticeReportRepository::report)
        .list();
  }

  public Optional<Report> find(UUID id) {
    return jdbc.sql(
            "select "
                + COLUMNS
                + " from notice.notice_reports r left join notice.notices n on n.id = r.notice_id left join notice.policy_judgments p on p.raw_policy_id = r.raw_policy_id"
                + " where r.id = :id")
        .param("id", id)
        .query(NoticeReportRepository::report)
        .optional();
  }

  /** 같은 대상(공고·사업·혜택 정책)·칸의 다른 제보 (오래된 것부터). 일반 제보(대상 없음)는 묶지 않아요. */
  public List<Report> sameGroup(Report target, UUID except) {
    if (target.noticeId() == null
        && target.rawPolicyId() == null
        && target.benefitPolicyId() == null) {
      return List.of();
    }
    return sameGroup(
        target.noticeId(), target.rawPolicyId(), target.benefitPolicyId(), target.field(), except);
  }

  private List<Report> sameGroup(
      UUID noticeId, UUID rawPolicyId, UUID benefitPolicyId, String field, UUID except) {
    return jdbc.sql(
            "select "
                + COLUMNS
                + " from notice.notice_reports r left join notice.notices n on n.id = r.notice_id left join notice.policy_judgments p on p.raw_policy_id = r.raw_policy_id"
                + " where r.notice_id is not distinct from cast(:notice as uuid) and"
                + " r.raw_policy_id is not distinct from cast(:program as uuid) and"
                + " r.benefit_policy_id is not distinct from cast(:benefit as uuid) and r.field ="
                + " :field and r.id <> :except order by r.created_at limit 50")
        .param("notice", noticeId)
        .param("program", rawPolicyId)
        .param("benefit", benefitPolicyId)
        .param("field", field)
        .param("except", except)
        .query(NoticeReportRepository::report)
        .list();
  }

  /** 상태별 건수: [NEW, DOING, DONE]. */
  public int[] counts() {
    int[] out = new int[3];
    jdbc.sql("select status, count(*) from notice.notice_reports group by status")
        .query(
            (rs, i) -> {
              int index =
                  switch (rs.getString(1)) {
                    case "NEW" -> 0;
                    case "DOING" -> 1;
                    default -> 2;
                  };
              out[index] = rs.getInt(2);
              return null;
            })
        .list();
    return out;
  }

  /** 처리 시작 (NEW → DOING). 바꾼 건수. */
  public int start(UUID id, String admin, Instant now) {
    return jdbc.sql(
            "update notice.notice_reports set status = 'DOING', started_at = :now, handled_by ="
                + " :admin where id = :id and status = 'NEW'")
        .param("id", id)
        .param("admin", admin)
        .param("now", OffsetDateTime.ofInstant(now, ZoneOffset.UTC))
        .update();
  }

  /**
   * 처리 끝 (DONE). ids 중 아직 끝나지 않은 것만 바꾸고, 바꾼 제보를 돌려줘요(답장 이벤트용).
   *
   * @param result FIXED · KEPT
   */
  public List<Report> finish(
      List<UUID> ids, String result, String reply, String admin, Instant now) {
    if (ids.isEmpty()) {
      return List.of();
    }
    List<UUID> changed =
        jdbc.sql(
                "update notice.notice_reports set status = 'DONE', result = :result, reply ="
                    + " :reply, handled_by = :admin, handled_at = :now, started_at ="
                    + " coalesce(started_at, :now) where id in (:ids) and status <> 'DONE'"
                    + " returning id")
            .param("ids", ids)
            .param("result", result)
            .param("reply", reply)
            .param("admin", admin)
            .param("now", OffsetDateTime.ofInstant(now, ZoneOffset.UTC))
            .query(UUID.class)
            .list();
    return changed.stream().map(this::find).flatMap(Optional::stream).toList();
  }

  /** 공고의 지금 원본 글 ID (공개된 공고만). */
  public Optional<UUID> currentRawPost(UUID noticeId) {
    return jdbc.sql(
            "select current_raw_post_id from notice.notices where id = :id and current_version > 0")
        .param("id", noticeId)
        .query(UUID.class)
        .optional();
  }

  /** 다시 연 검수를 제보들에 잇고, 새 제보면 처리 중으로. */
  public void linkReview(List<UUID> ids, UUID reviewJobId, String admin, Instant now) {
    jdbc.sql(
            "update notice.notice_reports set review_job_id = :job, status = case when status ="
                + " 'NEW' then 'DOING' else status end, started_at = coalesce(started_at, :now),"
                + " handled_by = coalesce(handled_by, :admin) where id in (:ids) and status <>"
                + " 'DONE'")
        .param("ids", ids)
        .param("job", reviewJobId)
        .param("admin", admin)
        .param("now", OffsetDateTime.ofInstant(now, ZoneOffset.UTC))
        .update();
  }

  /** 탈퇴한 회원의 제보를 지워요. 지운 건수. */
  public int deleteByReporter(UUID reporterId) {
    return jdbc.sql("delete from notice.notice_reports where reporter_id = :r")
        .param("r", reporterId)
        .update();
  }

  private static Report report(ResultSet rs, int i) throws SQLException {
    return new Report(
        rs.getObject("id", UUID.class),
        rs.getObject("notice_id", UUID.class),
        rs.getObject("raw_policy_id", UUID.class),
        rs.getObject("benefit_policy_id", UUID.class),
        rs.getString("title"),
        rs.getObject("reporter_id", UUID.class),
        rs.getString("field"),
        rs.getString("current_value"),
        rs.getString("reported_value"),
        rs.getString("note"),
        rs.getString("screen"),
        rs.getString("status"),
        rs.getString("result"),
        rs.getString("reply"),
        rs.getString("handled_by"),
        rs.getObject("created_at", OffsetDateTime.class),
        rs.getObject("started_at", OffsetDateTime.class),
        rs.getObject("handled_at", OffsetDateTime.class),
        rs.getObject("review_job_id", UUID.class),
        rs.getInt("open_in_group"));
  }

  /**
   * 넣을 제보. 대상은 noticeId·rawPolicyId·benefitPolicyId 중 하나만.
   *
   * @param targetTitle 혜택 정책 제목 (혜택 정책 제보만, 나머지는 null)
   */
  public record Row(
      UUID id,
      UUID noticeId,
      UUID rawPolicyId,
      UUID benefitPolicyId,
      String targetTitle,
      UUID reporterId,
      String field,
      String currentValue,
      String reportedValue,
      String note,
      String screen,
      Instant createdAt) {}

  /**
   * 저장된 제보.
   *
   * @param openInGroup 같은 공고·칸의 처리 전 제보 수 (이 제보 포함)
   */
  public record Report(
      UUID id,
      UUID noticeId,
      UUID rawPolicyId,
      UUID benefitPolicyId,
      String noticeTitle,
      UUID reporterId,
      String field,
      String currentValue,
      String reportedValue,
      String note,
      String screen,
      String status,
      String result,
      String reply,
      String handledBy,
      OffsetDateTime createdAt,
      OffsetDateTime startedAt,
      OffsetDateTime handledAt,
      UUID reviewJobId,
      int openInGroup) {}
}
