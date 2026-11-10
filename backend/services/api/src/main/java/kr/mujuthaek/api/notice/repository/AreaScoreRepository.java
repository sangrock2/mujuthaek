package kr.mujuthaek.api.notice.repository;

import java.math.BigDecimal;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.List;
import java.util.UUID;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

/** area가 계산한 위치별 점수 (notice.notice_area_scores). */
@Repository
public class AreaScoreRepository {

  private final JdbcClient jdbc;

  public AreaScoreRepository(JdbcClient jdbc) {
    this.jdbc = jdbc;
  }

  /** 저장해요. 이미 더 나중에 계산한 점수가 있으면 그대로 둬요 (늦게 도착한 옛 계산이 덮어쓰지 않게). */
  public int upsert(UUID noticeId, int noticeVersion, ScoreRow row, Instant now) {
    return jdbc.sql(
            "insert into notice.notice_area_scores (notice_id, notice_version, location_id, kind, score,"
                + " calculated_at, calculation_version, received_at) values (:noticeId,"
                + " :noticeVersion, :locationId, :kind, :score, :calculatedAt, :version, :now)"
                + " on conflict (notice_id, location_id, kind) do update set score = excluded.score,"
                + " calculated_at = excluded.calculated_at,"
                + " calculation_version = excluded.calculation_version,"
                + " received_at = excluded.received_at"
                + ", notice_version = excluded.notice_version"
                + " where notice.notice_area_scores.notice_version is null"
                + " or notice.notice_area_scores.notice_version < excluded.notice_version"
                + " or (notice.notice_area_scores.notice_version = excluded.notice_version"
                + " and notice.notice_area_scores.calculated_at <= excluded.calculated_at)")
        .param("noticeId", noticeId)
        .param("noticeVersion", noticeVersion)
        .param("locationId", row.locationId())
        .param("kind", row.kind())
        .param("score", row.score())
        .param("calculatedAt", row.calculatedAt().atOffset(ZoneOffset.UTC))
        .param("version", row.calculationVersion())
        .param("now", now.atOffset(ZoneOffset.UTC))
        .update();
  }

  /**
   * 공고의 점수 중 계산한 버전과 지금 버전의 위치 내용이 같은 것. 지금 버전에서 보류한 위치는 여기서 거르지 않아요: 조회하는 쪽이
   * NoticeContent.locationIds(스냅샷)로 걸러요.
   */
  public List<ScoreRow> findByNotice(UUID noticeId) {
    return jdbc.sql(
            "select s.location_id, s.kind, s.score, s.calculated_at, s.calculation_version"
                + " from notice.notice_area_scores s join notice.notices n on n.id = s.notice_id"
                + " join notice.notice_versions iv on iv.notice_id = s.notice_id and iv.version = s.notice_version"
                + " join notice.notice_versions cv on cv.notice_id = n.id and cv.version = n.current_version"
                + " where s.notice_id = :id and iv.payload->'notice'->'locations' = cv.payload->'notice'->'locations'"
                + " order by s.location_id, s.kind")
        .param("id", noticeId)
        .query(
            (rs, i) ->
                new ScoreRow(
                    rs.getString("location_id"),
                    rs.getString("kind"),
                    rs.getBigDecimal("score"),
                    rs.getObject("calculated_at", OffsetDateTime.class).toInstant(),
                    rs.getString("calculation_version")))
        .list();
  }

  public record ScoreRow(
      String locationId,
      String kind,
      BigDecimal score,
      Instant calculatedAt,
      String calculationVersion) {}
}
