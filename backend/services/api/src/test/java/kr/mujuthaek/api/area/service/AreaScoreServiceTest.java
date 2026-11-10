package kr.mujuthaek.api.area.service;

import static kr.mujuthaek.api.area.AreaTestDatabase.exec;
import static kr.mujuthaek.api.area.AreaTestDatabase.one;
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.List;
import java.util.Map;
import java.util.UUID;
import javax.sql.DataSource;
import kr.mujuthaek.api.area.AreaTestDatabase;
import kr.mujuthaek.api.area.domain.Coordinate;
import kr.mujuthaek.api.area.domain.LifeCategory;
import kr.mujuthaek.api.area.domain.SiteScore;
import kr.mujuthaek.api.area.repository.PostgresLifeScoreCalculator;
import kr.mujuthaek.api.area.repository.PostgresLocationScores;
import kr.mujuthaek.api.area.repository.PostgresNoticeLocations;
import kr.mujuthaek.api.area.repository.PostgresScoreRules;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class AreaScoreServiceTest {

  private final DataSource ds = AreaTestDatabase.dataSource();
  private final AreaScoreService service =
      new AreaScoreService(
          new PostgresNoticeLocations(ds),
          new PostgresLocationScores(ds),
          new PostgresScoreRules(ds),
          new LifeScoreService(new PostgresLifeScoreCalculator(ds), "2026.1"));
  private final UUID notice = UUID.randomUUID();
  private UUID site;
  private UUID noCoordinate;

  @BeforeEach
  void sites() throws Exception {
    site =
        UUID.fromString(
            one(
                "insert into area.notice_locations (notice_id, notice_location_id, notice_version, kind,"
                    + " address_text, geom, status, method) values ('"
                    + notice
                    + "', 'a', 1, 'COMPLEX', '주소', st_makepoint(127.0, 37.5)::geography, 'OK', 'FILE')"
                    + " returning location_id"));
    noCoordinate =
        UUID.fromString(
            one(
                "insert into area.notice_locations (notice_id, notice_location_id, notice_version, kind,"
                    + " address_text, status, fail_reason) values ('"
                    + notice
                    + "', 'b', 1, 'COMPLEX', '주소', 'FAILED', 'NOT_FOUND') returning location_id"));
    exec(
        "insert into area.location_scores (location_id, score_kind, category, score, score_version)"
            + " select '"
            + site
            + "', 'LIFE', c, s, '2026.1' from (values ('TRANSIT', 80), ('SCHOOL', 60), ('PARK', 40),"
            + " ('CONVENIENCE', 20), ('HOSPITAL', 0)) v(c, s)");
  }

  @AfterEach
  void clean() throws Exception {
    exec("delete from area.notice_locations where notice_id = '" + notice + "'");
  }

  /** 위치에서 정북으로 정확히 meters만큼 떨어진 점. */
  private Coordinate north(int meters) throws Exception {
    String[] p =
        one("select st_y(p)||','||st_x(p) from (select st_project(geom, "
                + meters
                + ", 0)::geometry p from area.notice_locations where location_id = '"
                + site
                + "') x")
            .split(",");
    return new Coordinate(Double.parseDouble(p[0]), Double.parseDouble(p[1]));
  }

  @Test
  void withoutWeightsEveryCategoryCountsTheSame() {
    SiteScore s = service.score(List.of(site), Map.of(), null).getFirst();

    assertThat(s.total()).isEqualTo(40); // (80 + 60 + 40 + 20 + 0) ÷ 5
    assertThat(s.categoryScores()).hasSize(5).containsEntry(LifeCategory.TRANSIT, 80);
    assertThat(s.commuteMeters()).isNull();
    assertThat(s.commuteMinutes()).isNull();
  }

  @Test
  void weightsDecideTheTotal() {
    var onlyTransit = Map.of(LifeCategory.TRANSIT, 10, LifeCategory.PARK, 0);
    assertThat(service.score(List.of(site), onlyTransit, null).getFirst().total()).isEqualTo(80);

    var transitAndPark = Map.of(LifeCategory.TRANSIT, 3, LifeCategory.PARK, 1);
    // (80×3 + 40×1) ÷ 4 = 70
    assertThat(service.score(List.of(site), transitAndPark, null).getFirst().total()).isEqualTo(70);
  }

  @Test
  void workplaceDistanceBecomesTheWorkScore() throws Exception {
    Coordinate fiveKm = north(5000);

    SiteScore s = service.score(List.of(site), Map.of(LifeCategory.WORK, 10), fiveKm).getFirst();

    assertThat(s.commuteMeters()).isEqualTo(5000L);
    assertThat(s.categoryScores()).containsEntry(LifeCategory.WORK, 90); // 3km 100 ~ 7km 80 사이
    assertThat(s.total()).isEqualTo(90);
    // 같은 입력이면 같은 점수
    assertThat(service.score(List.of(site), Map.of(LifeCategory.WORK, 10), fiveKm))
        .containsExactly(s);
    // 같은 비중이면 직장도 한 항목: (200 + 90) ÷ 6 = 48.3 → 48
    assertThat(service.score(List.of(site), Map.of(), fiveKm).getFirst().total()).isEqualTo(48);
  }

  @Test
  void unknownSitesAreLeftOutAndSitesWithoutCoordinatesHaveNoTotal() throws Exception {
    List<SiteScore> out =
        service.score(List.of(UUID.randomUUID(), noCoordinate, site, site), Map.of(), north(1000));

    assertThat(out).extracting(SiteScore::siteId).containsExactly(noCoordinate, site);
    assertThat(out.getFirst().total()).isNull();
    assertThat(out.getFirst().commuteMeters()).isNull();
    assertThat(out.getFirst().categoryScores()).isEmpty();
  }

  @Test
  void weightsOutsideZeroToTenAreRejected() {
    assertThatThrownBy(() -> service.score(List.of(site), Map.of(LifeCategory.PARK, 11), null))
        .isInstanceOf(IllegalArgumentException.class);
  }
}
