package kr.mujuthaek.api.area.repository;

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

/** 생활권 제보 (area.area_reports). 공고 제보(notice)와 같은 모양이에요. */
@Repository
public class AreaReportRepository {

  private static final String COLUMNS =
      "r.id, r.notice_id, r.notice_location_id, r.reporter_id, r.field, r.current_value,"
          + " r.reported_value, r.note, r.screen, r.status, r.result, r.reply, r.handled_by,"
          + " r.created_at, r.started_at, r.handled_at, (select count(*) from area.area_reports g"
          + " where g.notice_id = r.notice_id and g.field = r.field and g.status <> 'DONE') as"
          + " open_in_group";

  private final JdbcClient jdbc;

  public AreaReportRepository(JdbcClient jdbc) {
    this.jdbc = jdbc;
  }

  /** 생활권 위치를 계산한 공고인지. */
  public boolean hasLocations(UUID noticeId) {
    return jdbc.sql("select exists (select 1 from area.notice_locations where notice_id = :id)")
        .param("id", noticeId)
        .query(Boolean.class)
        .single();
  }

  public int countSince(UUID reporterId, Instant since) {
    return jdbc.sql(
            "select count(*) from area.area_reports where reporter_id = :r and created_at >="
                + " :since")
        .param("r", reporterId)
        .param("since", OffsetDateTime.ofInstant(since, ZoneOffset.UTC))
        .query(Integer.class)
        .single();
  }

  /** 넣어요. 같은 회원·공고·항목의 처리 전 제보가 있으면 넣지 않고 false. */
  public boolean insert(Report row) {
    return jdbc.sql(
                "insert into area.area_reports (id, notice_id, notice_location_id, reporter_id,"
                    + " field, current_value, reported_value, note, screen, created_at) values"
                    + " (:id, :notice, :location, :reporter, :field, :current, :reported, :note,"
                    + " :screen, :now) on conflict do nothing")
            .param("id", row.id())
            .param("notice", row.noticeId())
            .param("location", row.noticeLocationId())
            .param("reporter", row.reporterId())
            .param("field", row.field())
            .param("current", row.currentValue())
            .param("reported", row.reportedValue())
            .param("note", row.note())
            .param("screen", row.screen())
            .param("now", row.createdAt())
            .update()
        == 1;
  }

  /** 최근 처리 끝낸 제보 (관리자 「처리 기록」, 처리한 시각 최근 순). */
  public List<Report> handledSince(java.time.Instant since, int limit) {
    return jdbc.sql(
            "select "
                + COLUMNS
                + " from area.area_reports r where r.status = 'DONE' and r.handled_at >= :since"
                + " order by r.handled_at desc limit :limit")
        .param("since", java.sql.Timestamp.from(since))
        .param("limit", limit)
        .query(AreaReportRepository::report)
        .list();
  }

  /** 한 회원이 보낸 생활권 제보 (최근 것부터) */
  public List<Report> byReporter(UUID reporterId, int limit) {
    return jdbc.sql(
            "select "
                + COLUMNS
                + " from area.area_reports r where r.reporter_id = :r order by r.created_at desc"
                + " limit :limit")
        .param("r", reporterId)
        .param("limit", limit)
        .query(AreaReportRepository::report)
        .list();
  }

  /** 그 상태의 제보를 최신순으로 limit건. before(들어온 시각·ID)가 있으면 그 건 다음(더 오래된 것)부터 (관리자 제보 대기열). */
  public List<Report> page(String status, OffsetDateTime beforeAt, UUID beforeId, int limit) {
    return jdbc.sql(
            "select "
                + COLUMNS
                + " from area.area_reports r where r.status = :status and (cast(:beforeAt as"
                + " timestamptz) is null or (r.created_at, r.id) < (cast(:beforeAt as timestamptz),"
                + " cast(:beforeId as uuid))) order by r.created_at desc, r.id desc limit :limit")
        .param("status", status)
        .param("beforeAt", beforeAt)
        .param("beforeId", beforeId)
        .param("limit", limit)
        .query(AreaReportRepository::report)
        .list();
  }

  public List<Report> list(String status, int limit) {
    return jdbc.sql(
            "select "
                + COLUMNS
                + " from area.area_reports r where (cast(:status as text) is null or r.status ="
                + " :status) order by r.created_at desc limit :limit")
        .param("status", status)
        .param("limit", limit)
        .query(AreaReportRepository::report)
        .list();
  }

  public Optional<Report> find(UUID id) {
    return jdbc.sql("select " + COLUMNS + " from area.area_reports r where r.id = :id")
        .param("id", id)
        .query(AreaReportRepository::report)
        .optional();
  }

  public List<Report> sameGroup(UUID noticeId, String field, UUID except) {
    return jdbc.sql(
            "select "
                + COLUMNS
                + " from area.area_reports r where r.notice_id = :notice and r.field = :field and"
                + " r.id <> :except order by r.created_at limit 50")
        .param("notice", noticeId)
        .param("field", field)
        .param("except", except)
        .query(AreaReportRepository::report)
        .list();
  }

  /** 상태별 건수: [NEW, DOING, DONE]. */
  public int[] counts() {
    int[] out = new int[3];
    jdbc.sql("select status, count(*) from area.area_reports group by status")
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

  public int start(UUID id, String admin, Instant now) {
    return jdbc.sql(
            "update area.area_reports set status = 'DOING', started_at = :now, handled_by ="
                + " :admin where id = :id and status = 'NEW'")
        .param("id", id)
        .param("admin", admin)
        .param("now", OffsetDateTime.ofInstant(now, ZoneOffset.UTC))
        .update();
  }

  /** 처리 끝. 바꾼 제보를 돌려줘요(답장 이벤트용). */
  public List<Report> finish(
      List<UUID> ids, String result, String reply, String admin, Instant now) {
    if (ids.isEmpty()) {
      return List.of();
    }
    List<UUID> changed =
        jdbc.sql(
                "update area.area_reports set status = 'DONE', result = :result, reply = :reply,"
                    + " handled_by = :admin, handled_at = :now, started_at = coalesce(started_at,"
                    + " :now) where id in (:ids) and status <> 'DONE' returning id")
            .param("ids", ids)
            .param("result", result)
            .param("reply", reply)
            .param("admin", admin)
            .param("now", OffsetDateTime.ofInstant(now, ZoneOffset.UTC))
            .query(UUID.class)
            .list();
    return changed.stream().map(this::find).flatMap(Optional::stream).toList();
  }

  public int deleteByReporter(UUID reporterId) {
    return jdbc.sql("delete from area.area_reports where reporter_id = :r")
        .param("r", reporterId)
        .update();
  }

  private static Report report(ResultSet rs, int i) throws SQLException {
    return new Report(
        rs.getObject("id", UUID.class),
        rs.getObject("notice_id", UUID.class),
        rs.getString("notice_location_id"),
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
        rs.getInt("open_in_group"));
  }

  /** 생활권 제보 한 건. 넣을 때는 상태·처리 칸과 openInGroup을 비워요. */
  public record Report(
      UUID id,
      UUID noticeId,
      String noticeLocationId,
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
      int openInGroup) {}
}
