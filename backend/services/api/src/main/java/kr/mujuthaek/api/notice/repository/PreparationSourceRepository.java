package kr.mujuthaek.api.notice.repository;

import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.util.Collection;
import java.util.List;
import java.util.UUID;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

/** 준비함용 공개 원본. 현재 버전과 후속 안내를 한 SQL snapshot으로 일괄 조회한다. */
@Repository
public class PreparationSourceRepository {
  private final JdbcClient jdbc;

  public PreparationSourceRepository(JdbcClient jdbc) {
    this.jdbc = jdbc;
  }

  public record SourceRow(
      UUID requestedId,
      UUID id,
      String field,
      String title,
      String provider,
      String status,
      LocalDate applyStart,
      LocalDate applyEnd,
      String detailUrl,
      int version,
      boolean reviewed,
      OffsetDateTime updatedAt,
      String payload,
      String followUps) {}

  public List<SourceRow> findAll(Collection<UUID> ids) {
    if (ids.isEmpty()) return List.of();
    return jdbc.sql(
            """
        select m.id requested_id, n.id, n.field, n.title, n.provider, n.status,
          n.apply_start, n.apply_end, n.detail_url, n.current_version, n.reviewed, n.updated_at,
          v.payload::text payload,
          coalesce((select jsonb_agg(jsonb_build_object('title', f.title, 'detailUrl', f.detail_url,
            'postedOn', f.posted_on, 'schedules', f.schedules) order by f.raw_post_id)
            from notice.notice_follow_ups f where f.notice_id = n.id), '[]'::jsonb)::text follow_ups
        from notice.notices m
        join notice.notices n on n.id = coalesce(m.merged_into, m.id)
        join notice.notice_versions v on v.notice_id = n.id and v.version = n.current_version
        where m.id in (:ids) and n.current_version > 0 and not n.hidden
        """)
        .param("ids", ids)
        .query(
            (rs, i) ->
                new SourceRow(
                    rs.getObject("requested_id", UUID.class),
                    rs.getObject("id", UUID.class),
                    rs.getString("field"),
                    rs.getString("title"),
                    rs.getString("provider"),
                    rs.getString("status"),
                    rs.getObject("apply_start", LocalDate.class),
                    rs.getObject("apply_end", LocalDate.class),
                    rs.getString("detail_url"),
                    rs.getInt("current_version"),
                    rs.getBoolean("reviewed"),
                    rs.getObject("updated_at", OffsetDateTime.class),
                    rs.getString("payload"),
                    rs.getString("follow_ups")))
        .list();
  }
}
