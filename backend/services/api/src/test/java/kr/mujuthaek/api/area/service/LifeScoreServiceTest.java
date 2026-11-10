package kr.mujuthaek.api.area.service;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import java.util.UUID;
import kr.mujuthaek.api.area.AreaTestDatabase;
import kr.mujuthaek.api.area.repository.PostgresLifeScoreCalculator;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;

/** 설정한 규칙 버전으로 계산하는지. 점수 값 자체는 PostgresLifeScoreCalculatorTest가 봐요. */
class LifeScoreServiceTest {

  private final LifeScoreService service =
      new LifeScoreService(
          new PostgresLifeScoreCalculator(AreaTestDatabase.dataSource()), "2026.1");

  @AfterEach
  void deleteLocations() throws Exception {
    AreaTestDatabase.exec("delete from area.notice_locations where address_text = '시험 위치 점수 서비스'");
  }

  @Test
  void recalculatesWithConfiguredVersion() throws Exception {
    UUID at = UUID.randomUUID();
    AreaTestDatabase.exec(
        "insert into area.notice_locations (location_id, notice_id, notice_location_id, notice_version, kind,"
            + " address_text, geom, status, method) values ('"
            + at
            + "', gen_random_uuid(), 'building-a', 1, 'COMPLEX', '시험 위치 점수 서비스',"
            + " st_makepoint(126.1, 35.1)::geography, 'OK', 'FILE')");

    assertThat(service.scoreVersion()).isEqualTo("2026.1");
    assertThat(service.recalculate(List.of())).isZero();
    // 지표가 없어도 항목 5개는 0점으로 저장돼요
    assertThat(service.recalculate(List.of(at))).isEqualTo(5);
    assertThat(service.recalculateAll()).isGreaterThanOrEqualTo(5);
    assertThat(
            AreaTestDatabase.one(
                "select string_agg(distinct score_version, ',') from area.location_scores"
                    + " where location_id = '"
                    + at
                    + "'"))
        .isEqualTo("2026.1");
  }
}
