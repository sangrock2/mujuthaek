package kr.mujuthaek.api.area.repository;

import static kr.mujuthaek.api.area.AreaTestDatabase.exec;
import static org.assertj.core.api.Assertions.assertThat;

import java.math.BigDecimal;
import java.util.List;
import java.util.UUID;
import kr.mujuthaek.api.area.AreaTestDatabase;
import kr.mujuthaek.api.area.domain.LifeCategory;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;

class PostgresLocationScoresTest {

  private final PostgresLocationScores scores =
      new PostgresLocationScores(AreaTestDatabase.dataSource());
  private final UUID notice = UUID.randomUUID();

  @AfterEach
  void clean() throws Exception {
    exec("delete from area.notice_locations where notice_id = '" + notice + "'");
  }

  @Test
  void readsLifeCategoryScoresOfEachLocation() throws Exception {
    UUID withScores = location("a");
    UUID without = location("b");
    exec(
        "insert into area.location_scores (location_id, score_kind, category, score, score_version) values"
            + " ('"
            + withScores
            + "', 'LIFE', 'TRANSIT', 80, '2026.1'),"
            + " ('"
            + withScores
            + "', 'LIFE', 'PARK', 41, '2026.1'),"
            + " ('"
            + withScores
            + "', 'COMMERCIAL', 'DENSITY', 10, '2026.1')");

    var read = scores.lifeScores(List.of(withScores, without));

    assertThat(read).containsOnlyKeys(withScores);
    assertThat(read.get(withScores).scores())
        .containsEntry(LifeCategory.TRANSIT, BigDecimal.valueOf(80))
        .containsEntry(LifeCategory.PARK, BigDecimal.valueOf(41))
        .hasSize(2); // 상권 점수는 빼요
    assertThat(read.get(withScores).scoreVersion()).isEqualTo("2026.1");
    assertThat(read.get(withScores).calculatedAt()).isNotNull();
    assertThat(scores.lifeScores(List.of())).isEmpty();
  }

  private UUID location(String id) throws Exception {
    return UUID.fromString(
        AreaTestDatabase.one(
            "insert into area.notice_locations (notice_id, notice_location_id, notice_version, kind,"
                + " address_text, status) values ('"
                + notice
                + "', '"
                + id
                + "', 1, 'COMPLEX', '주소', 'APPROX') returning location_id"));
  }
}
