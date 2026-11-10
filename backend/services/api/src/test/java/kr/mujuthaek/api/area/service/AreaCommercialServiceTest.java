package kr.mujuthaek.api.area.service;

import static kr.mujuthaek.api.area.AreaTestDatabase.exec;
import static kr.mujuthaek.api.area.AreaTestDatabase.one;
import static org.assertj.core.api.Assertions.assertThat;

import java.math.BigDecimal;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.UUID;
import javax.sql.DataSource;
import kr.mujuthaek.api.area.AreaTestDatabase;
import kr.mujuthaek.api.area.domain.CommercialIndustry;
import kr.mujuthaek.api.area.domain.CommercialScore;
import kr.mujuthaek.api.area.repository.PostgresCommercialMeasures;
import kr.mujuthaek.api.area.repository.PostgresCommercialMeasures.Measures;
import kr.mujuthaek.api.area.repository.PostgresLifeScoreCalculator;
import kr.mujuthaek.api.area.repository.PostgresScoreRules;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

/** 공공 상가 위치 하나 둘레에 시험 점포·역을 놓고 상권 점수를 재요. 시험 자료는 제주 남쪽 바다 위(125.6, 33.0)라 다른 자료와 섞이지 않아요. */
class AreaCommercialServiceTest {

  private static final Instant NOW = Instant.parse("2026-10-25T03:00:00Z");
  private final DataSource ds = AreaTestDatabase.dataSource();
  private final AreaCommercialService service =
      new AreaCommercialService(
          new PostgresCommercialMeasures(ds),
          new PostgresScoreRules(ds),
          new LifeScoreService(new PostgresLifeScoreCalculator(ds), "2026.1"),
          Clock.fixed(NOW, ZoneOffset.UTC));
  private final UUID notice = UUID.randomUUID();
  private UUID site;

  @BeforeEach
  void shop() throws Exception {
    clean();
    site =
        UUID.fromString(
            one(
                "insert into area.notice_locations (notice_id, notice_location_id, notice_version, kind,"
                    + " address_text, geom, status, method) values ('"
                    + notice
                    + "', 'shop', 1, 'BUILDING', '공공 상가', st_makepoint(125.6, 33.0)::geography, 'OK', 'FILE')"
                    + " returning location_id"));
    // 300m 안 10개: 카페 4, 음식점 3, 소매(G2) 1, 그 밖 2 / 300m 밖 카페 1
    store("c1", "CAFE", "I2", 50);
    store("c2", "CAFE", "I2", 80);
    store("c3", "CAFE", "I2", 120);
    store("c4", "CAFE", "I2", 200);
    store("f1", "FOOD", "I2", 60);
    store("f2", "FOOD", "I2", 90);
    store("f3", "FOOD", "I2", 250);
    store("r1", "G2", "G2", 100);
    store("o1", "BAR", "I2", 150);
    store("o2", "MART", "G2", 280);
    store("far", "CAFE", "I2", 900);
    exec(
        "insert into area.facilities (kind, name, geom, source, source_key, data_date) select"
            + " 'SUBWAY_STATION', '시험상가역', st_project(st_makepoint(125.6, 33.0)::geography, 600, 0),"
            + " 'TEST_COMMERCIAL', 'st1', date '2026-09-30'");
    // 전국 비율: 카페 10%, 음식점 20%, 소매 5%
    exec(
        "insert into area.industry_shares (industry, store_count, total_count) values"
            + " ('CAFE', 100, 1000), ('FOOD', 200, 1000), ('RETAIL', 50, 1000)"
            + " on conflict (industry) do update set store_count = excluded.store_count,"
            + " total_count = excluded.total_count");
  }

  @AfterEach
  void clean() throws Exception {
    exec("delete from area.notice_locations where notice_id = '" + notice + "'");
    exec("delete from area.stores where load_scope = 'TEST_COMMERCIAL'");
    exec("delete from area.facilities where source = 'TEST_COMMERCIAL'");
  }

  /** 상가에서 정북으로 meters만큼 떨어진 시험 점포. */
  private static void store(String key, String group, String large, int meters) throws Exception {
    exec(
        "insert into area.stores (source_key, load_scope, name, large_code, industry_group, geom, data_date)"
            + " select 'TC-"
            + key
            + "', 'TEST_COMMERCIAL', '"
            + key
            + "', '"
            + large
            + "', '"
            + group
            + "', st_project(st_makepoint(125.6, 33.0)::geography, "
            + meters
            + ", 0), date '2026-09-30'");
  }

  @Test
  void cafeIsCrowdedSoCompetitionScoresLow() {
    CommercialScore s = service.score(site, "CAFE").orElseThrow();

    assertThat(s.stores300m()).isEqualTo(10);
    assertThat(s.sameIndustry300m()).isEqualTo(4);
    assertThat(s.industryGroup()).isEqualTo(CommercialIndustry.CAFE);
    // 입지계수 (4/10) ÷ 10% = 4 → 2.5 넘어서 0점
    assertThat(s.scores()).containsEntry("COMPETITION", 0);
    // 밀도 10곳: 0~30 사이 0→50 직선 → 16.7 → 17
    assertThat(s.scores()).containsEntry("DENSITY", 17);
    // 역 600m: 500 85 ~ 1000 55 사이 → 79
    assertThat(s.scores()).containsEntry("TRANSIT", 79);
    assertThat(s.score()).isEqualTo(32); // (17 + 0 + 79) ÷ 3 = 32
    assertThat(s.nearestStation().name()).isEqualTo("시험상가역");
    assertThat(s.nearestStation().meters()).isEqualTo(600);
    assertThat(s.nearestStation().walkMinutes()).isEqualTo(12); // 600 × 1.3 ÷ 67 = 11.6 → 12
    assertThat(s.households()).isNull();
    assertThat(s.calculatedAt().toString()).isEqualTo("2026-10-25T12:00+09:00");
  }

  @Test
  void retailCountsTheLargeCategoryG2() {
    CommercialScore s = service.score(site, "retail").orElseThrow();

    assertThat(s.sameIndustry300m()).isEqualTo(2); // G2 대분류 2곳 (마트 포함)
    // (2/10) ÷ 5% = 4 → 0점
    assertThat(s.scores()).containsEntry("COMPETITION", 0);
  }

  @Test
  void anIndustryWithoutAGroupHasNoCompetitionScore() {
    CommercialScore s = service.score(site, "STUDY_ROOM").orElseThrow();

    assertThat(s.industryGroup()).isNull();
    assertThat(s.sameIndustry300m()).isNull();
    assertThat(s.scores()).containsOnlyKeys("DENSITY", "TRANSIT");
    assertThat(s.score()).isEqualTo(48); // (17 + 79) ÷ 2
    assertThat(service.score(site, null).orElseThrow().scores()).doesNotContainKey("COMPETITION");
  }

  @Test
  void locationQuotientIsNullWithoutStoresOrShare() {
    assertThat(
            AreaCommercialService.locationQuotient(new Measures(0, 0L, BigDecimal.ONE, null, null)))
        .isNull();
    assertThat(AreaCommercialService.locationQuotient(new Measures(10, 2L, null, null, null)))
        .isNull();
    assertThat(
            AreaCommercialService.locationQuotient(
                new Measures(10, 2L, new BigDecimal("0.2"), null, null)))
        .isEqualByComparingTo("1");
  }

  @Test
  void unknownSiteOrSiteWithoutCoordinatesIsEmpty() throws Exception {
    assertThat(service.score(UUID.randomUUID(), "CAFE")).isEmpty();
    exec(
        "update area.notice_locations set geom = null, status = 'FAILED' where location_id = '"
            + site
            + "'");
    assertThat(service.score(site, "CAFE")).isEmpty();
  }
}
