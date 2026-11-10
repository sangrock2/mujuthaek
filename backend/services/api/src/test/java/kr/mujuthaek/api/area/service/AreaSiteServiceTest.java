package kr.mujuthaek.api.area.service;

import static kr.mujuthaek.api.area.AreaTestDatabase.exec;
import static kr.mujuthaek.api.area.AreaTestDatabase.one;
import static org.assertj.core.api.Assertions.assertThat;

import java.util.UUID;
import javax.sql.DataSource;
import kr.mujuthaek.api.area.AreaTestDatabase;
import kr.mujuthaek.api.area.domain.AreaCriteria;
import kr.mujuthaek.api.area.domain.AreaTag;
import kr.mujuthaek.api.area.domain.LifeCategory;
import kr.mujuthaek.api.area.domain.SiteDetail;
import kr.mujuthaek.api.area.repository.PostgresLifeScoreCalculator;
import kr.mujuthaek.api.area.repository.PostgresLocationScores;
import kr.mujuthaek.api.area.repository.PostgresNoticeLocations;
import kr.mujuthaek.api.area.repository.PostgresSiteDetails;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

/** 시험 위치는 제주 남쪽 바다 위(125.7, 33.0)라 다른 자료와 섞이지 않아요. */
class AreaSiteServiceTest {

  private final DataSource ds = AreaTestDatabase.dataSource();
  private final AreaSiteService service =
      new AreaSiteService(
          new PostgresNoticeLocations(ds),
          new PostgresSiteDetails(ds),
          new PostgresLocationScores(ds),
          new LifeScoreService(new PostgresLifeScoreCalculator(ds), "2026.1"));
  private final UUID notice = UUID.randomUUID();
  private UUID site;

  @BeforeEach
  void site() throws Exception {
    clean();
    site =
        UUID.fromString(
            one(
                "insert into area.notice_locations (notice_id, notice_location_id, notice_version, kind,"
                    + " address_text, geom, status, method) values ('"
                    + notice
                    + "', 'a', 1, 'COMPLEX', '주소', st_makepoint(125.7, 33.0)::geography, 'OK', 'FILE')"
                    + " returning location_id"));
    exec(
        "insert into area.location_metrics (location_id, metric, value) select '"
            + site
            + "', m, v from (values ('station_nearest_m', 420.4), ('station_count_1km', 1),"
            + " ('bus_stop_count_300m', 5), ('convenience_store_count_300m', 7),"
            + " ('park_nearest_m', 900), ('store_count_300m', 40)) x(m, v)");
    exec(
        "insert into area.facilities (kind, name, geom, source, source_key, data_date) select"
            + " 'SUBWAY_STATION', '시험바다역', st_project(st_makepoint(125.7, 33.0)::geography, 420, 0),"
            + " 'TEST_SITE', 'st1', date '2026-09-30'");
    exec(
        "insert into area.location_scores (location_id, score_kind, category, score, score_version)"
            + " values ('"
            + site
            + "', 'LIFE', 'TRANSIT', 90, '2026.1'), ('"
            + site
            + "', 'LIFE', 'PARK', 63, '2026.1')");
  }

  @AfterEach
  void clean() throws Exception {
    exec("delete from area.notice_locations where notice_id = '" + notice + "'");
    exec("delete from area.facilities where source = 'TEST_SITE'");
  }

  @Test
  void returnsCoordinatesMetricsScoresAndTags() {
    SiteDetail s = service.site(site).orElseThrow();

    assertThat(s.lat()).isEqualTo(33.0);
    assertThat(s.lng()).isEqualTo(125.7);
    assertThat(s.approximate()).isFalse();
    assertThat(s.metrics().nearestStation().name()).isEqualTo("시험바다역");
    assertThat(s.metrics().nearestStation().meters()).isEqualTo(420);
    assertThat(s.metrics().nearestStation().walkMinutes()).isEqualTo(9); // 420 × 1.3 ÷ 67 = 8.1 → 9
    assertThat(s.metrics().busStops300m()).isEqualTo(5);
    assertThat(s.metrics().convenienceStores300m()).isEqualTo(7);
    assertThat(s.metrics().parkNearestM()).isEqualTo(900);
    assertThat(s.metrics().hospitalNearestM()).isNull(); // 근처에 없음
    assertThat(s.metrics().clinics500m()).isZero();
    assertThat(s.categoryScores())
        .containsEntry(LifeCategory.TRANSIT, 90)
        .containsEntry(LifeCategory.PARK, 63);
    assertThat(s.tags()).containsExactly(AreaTag.STATION, AreaTag.CONVENIENCE);
    assertThat(s.calculatedAt().getOffset().getId()).isEqualTo("+09:00");
  }

  @Test
  void aSiteWithoutCoordinatesOrUnknownIsEmpty() throws Exception {
    assertThat(service.site(UUID.randomUUID())).isEmpty();
    exec(
        "update area.notice_locations set geom = null, status = 'FAILED' where location_id = '"
            + site
            + "'");
    assertThat(service.site(site)).isEmpty();
  }

  @Test
  void criteriaShowRulesWeightsAndSources() {
    AreaCriteria c = service.criteria();

    assertThat(c.scoreVersion()).isEqualTo("2026.1");
    assertThat(c.rules()).anySatisfy(r -> assertThat(r.metric()).isEqualTo("work_distance_m"));
    assertThat(c.weights())
        .anySatisfy(
            w -> {
              assertThat(w.category()).isEqualTo("TRANSIT");
              assertThat(w.metric()).isEqualTo("station_nearest_m");
            });
    assertThat(c.sources())
        .anySatisfy(
            src -> {
              assertThat(src.provider()).isEqualTo("건강보험심사평가원");
              assertThat(src.licenseUrl()).contains("kogl.or.kr");
            });
  }
}
