package kr.mujuthaek.api.area.repository;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.Collection;
import java.util.EnumMap;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.UUID;
import javax.sql.DataSource;
import kr.mujuthaek.api.area.domain.LifeCategory;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

/** 저장된 생활권 항목 점수(area.location_scores, LIFE) 읽기. 총점은 요청 때 가중치로 계산해요({@code TotalScore}). */
@Component
public final class PostgresLocationScores {

  /** 위치 하나의 항목 점수와 계산 시각·규칙 버전. */
  public record LifeScores(
      Map<LifeCategory, BigDecimal> scores, Instant calculatedAt, String scoreVersion) {}

  private final JdbcTemplate jdbc;

  public PostgresLocationScores(DataSource dataSource) {
    this.jdbc = new JdbcTemplate(dataSource);
  }

  /** 위치 ID → 항목 점수. 점수가 없는 위치는 빠져요. */
  public Map<UUID, LifeScores> lifeScores(Collection<UUID> locationIds) {
    Map<UUID, LifeScores> out = new LinkedHashMap<>();
    if (locationIds.isEmpty()) {
      return out;
    }
    jdbc.query(
        "select location_id, category, score, score_version, calculated_at from area.location_scores"
            + " where score_kind = 'LIFE' and location_id = any(?::uuid[]) order by location_id, category",
        rs -> {
          UUID id = rs.getObject("location_id", UUID.class);
          LifeCategory category = LifeCategory.valueOf(rs.getString("category"));
          Instant at = rs.getTimestamp("calculated_at").toInstant();
          LifeScores current = out.get(id);
          Map<LifeCategory, BigDecimal> scores =
              current == null ? new EnumMap<>(LifeCategory.class) : current.scores();
          scores.put(category, BigDecimal.valueOf(rs.getInt("score")));
          Instant latest =
              current == null || at.isAfter(current.calculatedAt()) ? at : current.calculatedAt();
          out.put(id, new LifeScores(scores, latest, rs.getString("score_version")));
        },
        (Object) locationIds.toArray(UUID[]::new));
    return out;
  }
}
