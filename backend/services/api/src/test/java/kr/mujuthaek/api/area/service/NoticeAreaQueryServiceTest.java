package kr.mujuthaek.api.area.service;

import static kr.mujuthaek.api.area.AreaTestDatabase.exec;
import static kr.mujuthaek.api.area.AreaTestDatabase.one;
import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import java.util.UUID;
import javax.sql.DataSource;
import kr.mujuthaek.api.area.AreaTestDatabase;
import kr.mujuthaek.api.area.repository.PostgresLocationScores;
import kr.mujuthaek.api.area.repository.PostgresNoticeLocations;
import kr.mujuthaek.api.area.repository.PostgresSiteDetails;
import kr.mujuthaek.api.area.service.NoticeAreaQueryService.NoticePoint;
import kr.mujuthaek.api.area.service.NoticeAreaQueryService.NoticeSite;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

/** 시험 위치는 동해 바다 위(131.x, 37.x)라 다른 자료와 섞이지 않아요. */
class NoticeAreaQueryServiceTest {

  private final DataSource ds = AreaTestDatabase.dataSource();
  private final NoticeAreaQueryService query =
      new NoticeAreaQueryService(
          new PostgresNoticeLocations(ds),
          new PostgresSiteDetails(ds),
          new PostgresLocationScores(ds));
  private final UUID first = UUID.randomUUID();
  private final UUID second = UUID.randomUUID();
  private UUID a;

  @BeforeEach
  void locations() throws Exception {
    a = location(first, "building-a", "st_makepoint(131.10, 37.10)", "OK");
    location(first, "building-b", "null", "FAILED");
    location(second, "site-1", "st_makepoint(131.50, 37.50)", "APPROX");
    exec(
        "insert into area.location_metrics (location_id, metric, value) values ('"
            + a
            + "', 'station_nearest_m', 300), ('"
            + a
            + "', 'convenience_store_count_300m', 4)");
    exec(
        "insert into area.location_scores (location_id, score_kind, category, score, score_version)"
            + " values ('"
            + a
            + "', 'LIFE', 'TRANSIT', 90, '2026.1'), ('"
            + a
            + "', 'LIFE', 'PARK', 61, '2026.1')");
  }

  @AfterEach
  void clean() throws Exception {
    exec(
        "delete from area.notice_locations where notice_id in ('" + first + "', '" + second + "')");
  }

  private static UUID location(UUID notice, String id, String geom, String status)
      throws Exception {
    return UUID.fromString(
        one(
            "insert into area.notice_locations (notice_id, notice_location_id, notice_version, kind,"
                + " address_text, geom, status, fail_reason) values ('"
                + notice
                + "', '"
                + id
                + "', 1, 'COMPLEX', '주소', "
                + geom
                + "::geography, '"
                + status
                + "', "
                + ("FAILED".equals(status) ? "'NOT_FOUND'" : "null")
                + ") returning location_id"));
  }

  @Test
  void sitesOfNoticesCarryCoordinatesTagsAndLivingScore() {
    var sites = query.sitesOf(List.of(first, second, UUID.randomUUID()));

    assertThat(sites).containsOnlyKeys(first, second);
    assertThat(sites.get(first))
        .extracting(NoticeSite::noticeLocationId)
        .containsExactly("building-a", "building-b");
    NoticeSite withArea = sites.get(first).getFirst();
    assertThat(withArea.siteId()).isEqualTo(a);
    assertThat(withArea.lat()).isEqualTo(37.10);
    assertThat(withArea.tags()).containsExactly("STATION", "CONVENIENCE");
    assertThat(withArea.livingScore()).isEqualTo(76); // (90 + 61) ÷ 2 = 75.5 → 76
    NoticeSite failed = sites.get(first).get(1);
    assertThat(failed.lat()).isNull();
    assertThat(failed.tags()).isEmpty();
    assertThat(failed.livingScore()).isNull();
    assertThat(sites.get(second).getFirst().approximate()).isTrue();
    assertThat(query.sitesOf(List.of())).isEmpty();
  }

  @Test
  void pointsWithinTheMapGiveOneRepresentativePerNotice() {
    List<NoticePoint> both = query.pointsWithin(37.0, 131.0, 37.6, 131.6, 100);
    assertThat(both).extracting(NoticePoint::noticeId).containsExactlyInAnyOrder(first, second);
    assertThat(both)
        .filteredOn(p -> p.noticeId().equals(first))
        .singleElement()
        .satisfies(p -> assertThat(p.lat()).isEqualTo(37.10));

    assertThat(query.pointsWithin(37.0, 131.0, 37.2, 131.2, 100))
        .extracting(NoticePoint::noticeId)
        .containsExactly(first);
    assertThat(query.pointsWithin(37.0, 131.0, 37.6, 131.6, 1)).hasSize(1);
  }
}
