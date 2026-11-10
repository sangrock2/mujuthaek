package kr.mujuthaek.api.common.region;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import kr.mujuthaek.api.TestDatabase;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;

class RegionTableTest {

  private final JdbcTemplate jdbc = new JdbcTemplate(TestDatabase.dataSource());

  @BeforeEach
  void clean() {
    jdbc.update("delete from common.regions where level = 'SIGUNGU'");
    jdbc.update("delete from common.regions");
  }

  @Test
  void storesSidoAndSigungu() {
    jdbc.update(
        "insert into common.regions (code, level, name, full_name, short_name, base_date)"
            + " values ('11', 'SIDO', '서울특별시', '서울특별시', '서울', '2026-07-01')");
    jdbc.update(
        "insert into common.regions (code, level, parent_code, name, full_name, base_date)"
            + " values ('11440', 'SIGUNGU', '11', '마포구', '서울특별시 마포구', '2026-07-01')");

    assertThat(
            jdbc.queryForObject(
                "select full_name from common.regions where code = '11440'", String.class))
        .isEqualTo("서울특별시 마포구");
  }

  @Test
  void rejectsMalformedCodesAndSigunguWithoutSido() {
    assertThatThrownBy(
            () ->
                jdbc.update(
                    "insert into common.regions (code, level, name, full_name, base_date)"
                        + " values ('1144', 'SIGUNGU', 'x', 'x', '2026-07-01')"))
        .hasMessageContaining("check");
    assertThatThrownBy(
            () ->
                jdbc.update(
                    "insert into common.regions (code, level, name, full_name, base_date)"
                        + " values ('11440', 'SIGUNGU', '마포구', '마포구', '2026-07-01')"))
        .hasMessageContaining("check");
  }
}
