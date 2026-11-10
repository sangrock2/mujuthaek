package kr.mujuthaek.api.area.repository;

import static kr.mujuthaek.api.area.AreaTestDatabase.exec;
import static org.assertj.core.api.Assertions.assertThat;

import kr.mujuthaek.api.area.AreaTestDatabase;
import kr.mujuthaek.api.area.domain.BoundaryCheck;
import kr.mujuthaek.api.area.domain.BoundaryCheck.Sigungu;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

/**
 * 시험 도형으로 경계 검사. 다른 테스트 자료와 겹치지 않게 바다 위(북위 34.0, 동경 125.0)에 코드 99990으로 놓아요.
 *
 * <pre>
 * 시군구 99990: 사각형(125.00~125.01, 34.00~34.01, 약 920m × 1.1km) 가운데 구멍(125.004~125.006, 34.004~34.006)
 *              + 둘째 조각(125.03~125.04, 34.00~34.01)
 * 법정동 99990101: 사각형의 왼쪽 절반(125.000~125.005)
 * 북위 34도에서 경도 0.001도 ≈ 92m
 * </pre>
 */
class PostgresRegionBoundaryCheckTest {

  private static final PostgresRegionBoundaryCheck check =
      new PostgresRegionBoundaryCheck(AreaTestDatabase.dataSource());

  @BeforeEach
  void insertShapes() throws Exception {
    deleteShapes();
    exec(
        "insert into area.region_boundaries (level, code, name, geom, data_date) values"
            + " ('SIG', '99990', '시험구', 'SRID=4326;MULTIPOLYGON("
            + "((125.00 34.00, 125.01 34.00, 125.01 34.01, 125.00 34.01, 125.00 34.00),"
            + " (125.004 34.004, 125.004 34.006, 125.006 34.006, 125.006 34.004, 125.004 34.004)),"
            + " ((125.03 34.00, 125.04 34.00, 125.04 34.01, 125.03 34.01, 125.03 34.00)))'::geography,"
            + " date '2026-09-30'),"
            + " ('EMD', '99990101', '시험동', 'SRID=4326;MULTIPOLYGON("
            + "((125.000 34.00, 125.005 34.00, 125.005 34.01, 125.000 34.01, 125.000 34.00)))'::geography,"
            + " date '2026-09-30')");
  }

  @AfterEach
  void deleteShapes() throws Exception {
    exec("delete from area.region_boundaries where code in ('99990', '99990101')");
  }

  @ParameterizedTest(name = "{0}")
  @CsvSource({
    "안, 34.002, 125.002, INSIDE",
    "구멍 안(어느 동도 아님), 34.005, 125.005, OUT_OF_REGION",
    "구멍 밖 같은 조각, 34.008, 125.008, INSIDE",
    "둘째 조각, 34.005, 125.035, INSIDE",
    "경계 밖 30m(50m 여유로 통과), 34.005, 125.010325, INSIDE",
    "경계 밖 100m, 34.005, 125.01108, OUT_OF_REGION"
  })
  void sigunguBoundaryWith50mTolerance(String name, double lat, double lng, Sigungu expected) {
    assertThat(check.check("99990", null, lat, lng).sigungu()).isEqualTo(expected);
  }

  @Test
  void legalDongOutsideIsOnlyMarkedNotFailed() {
    BoundaryCheck rightHalf = check.check("99990", "9999010100", 34.002, 125.008);

    assertThat(rightHalf.passed()).isTrue();
    assertThat(rightHalf.emdMismatch()).isTrue();
    assertThat(check.check("99990", "9999010100", 34.002, 125.002).emdMismatch()).isFalse();
    assertThat(check.check("99990", null, 34.002, 125.008).emdMismatch()).isFalse();
  }

  @Test
  void missingBoundaryIsNotAFailure() {
    BoundaryCheck unknown = check.check("99991", "9999110100", 34.002, 125.002);

    assertThat(unknown.sigungu()).isEqualTo(Sigungu.NO_BOUNDARY);
    assertThat(unknown.passed()).isTrue();
    assertThat(unknown.emdMismatch()).isFalse();
  }
}
