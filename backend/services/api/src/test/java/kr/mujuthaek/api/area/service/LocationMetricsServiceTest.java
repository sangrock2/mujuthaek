package kr.mujuthaek.api.area.service;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import java.util.UUID;
import kr.mujuthaek.api.area.AreaTestDatabase;
import kr.mujuthaek.api.area.repository.PostgresLocationMetricsCalculator;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;

/** 위치 몇 곳만 / 좌표 있는 위치 전부를 다시 계산하는지. 지표 값 자체는 PostgresLocationMetricsCalculatorTest가 봐요. */
class LocationMetricsServiceTest {

  private final LocationMetricsService service =
      new LocationMetricsService(
          new PostgresLocationMetricsCalculator(AreaTestDatabase.dataSource()));

  @AfterEach
  void deleteLocations() throws Exception {
    AreaTestDatabase.exec("delete from area.notice_locations where address_text = '시험 위치 서비스'");
  }

  @Test
  void recalculatesGivenLocationsAndAll() throws Exception {
    UUID at = UUID.randomUUID();
    AreaTestDatabase.exec(
        "insert into area.notice_locations (location_id, notice_id, notice_location_id, notice_version, kind,"
            + " address_text, geom, status, method) values ('"
            + at
            + "', gen_random_uuid(), 'building-a', 1, 'COMPLEX', '시험 위치 서비스',"
            + " st_makepoint(126.0, 35.0)::geography, 'APPROX', 'CENTROID')");

    assertThat(service.recalculate(List.of())).isZero();
    // 근처 시설이 없어도 수 지표(반경 안 0곳)는 늘 있어요
    assertThat(service.recalculate(List.of(at))).isPositive();
    assertThat(service.recalculateAll()).isGreaterThanOrEqualTo(service.recalculate(List.of(at)));
  }
}
