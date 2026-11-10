package kr.mujuthaek.api.area.repository;

import static kr.mujuthaek.api.area.AreaTestDatabase.exec;
import static kr.mujuthaek.api.area.AreaTestDatabase.one;
import static org.assertj.core.api.Assertions.assertThat;

import kr.mujuthaek.api.area.AreaTestDatabase;
import kr.mujuthaek.api.area.domain.Coordinate;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class PostgresLegalDongCentroidTest {

  private final PostgresLegalDongCentroid centroid =
      new PostgresLegalDongCentroid(AreaTestDatabase.dataSource());

  // ㄷ자 모양: 무게중심(125.005, 34.005 근처)은 가운데 빈 곳이라 경계 밖이에요
  private static final String U_SHAPE =
      "SRID=4326;MULTIPOLYGON(((125.000 34.000, 125.010 34.000, 125.010 34.002, 125.002 34.002,"
          + " 125.002 34.008, 125.010 34.008, 125.010 34.010, 125.000 34.010, 125.000 34.000)))";

  @BeforeEach
  void insertShape() throws Exception {
    deleteShape();
    exec(
        "insert into area.region_boundaries (level, code, name, geom, data_date) values"
            + " ('EMD', '99980101', '시험동', '"
            + U_SHAPE
            + "'::geography, date '2026-09-30')");
  }

  @AfterEach
  void deleteShape() throws Exception {
    exec("delete from area.region_boundaries where code = '99980101'");
  }

  @Test
  void pointIsInsideEvenForAConcaveShape() throws Exception {
    Coordinate p = centroid.find("9998010100").orElseThrow();
    assertThat(
            one(
                "select st_contains(st_geomfromewkt('"
                    + U_SHAPE
                    + "'), st_setsrid(st_makepoint("
                    + p.lng()
                    + ", "
                    + p.lat()
                    + "), 4326))"))
        .isEqualTo("t");
    // 리(끝이 00이 아님)는 그 읍·면(앞 8자리)의 점
    assertThat(centroid.find("9998010123")).contains(p);
  }

  @Test
  void findsByTheLegalDongNameInsideTheSigungu() {
    PostgresLegalDongCentroid.Named found = centroid.findByName("99980", "시험동").orElseThrow();
    assertThat(found.bjdCode()).isEqualTo("9998010100");
    assertThat(found.point()).isEqualTo(centroid.find("9998010100").orElseThrow());
    // 리가 붙으면 앞 이름(읍·면)으로
    assertThat(centroid.findByName("99980", "시험동 용기리")).isPresent();
    assertThat(centroid.findByName("99970", "시험동")).isEmpty(); // 다른 시군구
    assertThat(centroid.findByName("99980", "없는동")).isEmpty();
    assertThat(centroid.findByName(null, "시험동")).isEmpty();
    assertThat(centroid.findByName("99980", " ")).isEmpty();
  }

  @Test
  void emptyWithoutABoundaryOrAValidCode() {
    assertThat(centroid.find("9998020100")).isEmpty(); // 경계 없음
    assertThat(centroid.find("99980101")).isEmpty(); // 10자리 아님
    assertThat(centroid.find(null)).isEmpty();
  }
}
