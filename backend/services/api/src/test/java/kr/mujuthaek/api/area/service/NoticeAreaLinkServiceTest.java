package kr.mujuthaek.api.area.service;

import static kr.mujuthaek.api.area.AreaTestDatabase.exec;
import static kr.mujuthaek.api.area.AreaTestDatabase.one;
import static org.assertj.core.api.Assertions.assertThat;

import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.function.Function;
import kr.mujuthaek.api.area.AreaTestDatabase;
import kr.mujuthaek.api.area.domain.AreaSource;
import kr.mujuthaek.api.area.geocode.CoordOutcome;
import kr.mujuthaek.api.area.geocode.SearchOutcome;
import kr.mujuthaek.api.area.geocode.SearchOutcome.Reason;
import kr.mujuthaek.api.area.repository.PostgresAddressPointLookup;
import kr.mujuthaek.api.area.repository.PostgresLegalDongCentroid;
import kr.mujuthaek.api.area.repository.PostgresLifeScoreCalculator;
import kr.mujuthaek.api.area.repository.PostgresLocationMetricsCalculator;
import kr.mujuthaek.api.area.repository.PostgresLocationScores;
import kr.mujuthaek.api.area.repository.PostgresNoticeLocations;
import kr.mujuthaek.api.area.repository.PostgresRegionBoundaryCheck;
import kr.mujuthaek.api.area.repository.PostgresUtmkTransform;
import kr.mujuthaek.api.common.event.AreaScoresCalculated;
import kr.mujuthaek.api.common.event.NoticeLocationsChanged;
import kr.mujuthaek.api.common.event.NoticeLocationsChanged.Location;
import kr.mujuthaek.api.common.region.RegionQueryService;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;

/**
 * 공고 위치 이벤트 → 좌표 → 세권 지표 → 생활권 점수 → AreaScoresCalculated (실제 DB, 계산기 모두 진짜). 검색 API만 가짜예요. 시험 시군구는
 * 가짜 「26990」이고 사전 줄은 load_scope 97이라 끝나면 지워요.
 */
class NoticeAreaLinkServiceTest {

  private static final String BJD = "2699010100";

  private final List<Object> published = new ArrayList<>();
  private final List<String> searched = new ArrayList<>();
  private Function<String, SearchOutcome> answer = keyword -> new SearchOutcome.NotFound();
  private final UUID notice = UUID.randomUUID();
  private final javax.sql.DataSource ds = AreaTestDatabase.dataSource();

  private final NoticeAreaLinkService link =
      new NoticeAreaLinkService(
          new NoticeLocationService(
              new AddressLocator(
                  new PostgresAddressPointLookup(ds),
                  keyword -> {
                    searched.add(keyword);
                    return answer.apply(keyword);
                  },
                  building -> new CoordOutcome.Failed(Reason.NO_KEY, null),
                  new PostgresUtmkTransform(ds),
                  new PostgresLegalDongCentroid(ds),
                  new PostgresRegionBoundaryCheck(ds),
                  new RegionQueryService(new JdbcTemplate(ds))),
              new PostgresNoticeLocations(ds)),
          new PostgresNoticeLocations(ds),
          new LocationMetricsService(new PostgresLocationMetricsCalculator(ds)),
          new LifeScoreService(new PostgresLifeScoreCalculator(ds), "2026.1"),
          new PostgresLocationScores(ds),
          published::add);

  @BeforeEach
  void dictionary() throws Exception {
    clean();
    exec(
        "insert into area.address_points (address_id, load_scope, bjd_code, sigungu_code, road_code, road_name,"
            + " underground, bldg_main, bldg_sub, geom, data_date) values ('26990101999999900000700000', '97',"
            + " '"
            + BJD
            + "', '26990', '269909999999', '연결시험로', 0, 7, 0, st_makepoint(129.1, 35.2)::geography,"
            + " date '2026-09-30')");
  }

  @AfterEach
  void clean() throws Exception {
    exec("delete from area.notice_locations where notice_id = '" + notice + "'");
    exec("delete from area.address_points where load_scope = '97'");
  }

  private NoticeLocationsChanged event(int version, Location... locations) {
    return new NoticeLocationsChanged(notice, version, List.of(locations));
  }

  private static Location found(String id) {
    return new Location(id, "COMPLEX", BJD, "부산광역시 시험구 연결시험로 7", "시험단지");
  }

  private static Location notFound(String id) {
    return new Location(id, "BUILDING", null, "주소 별도 안내", null);
  }

  private List<AreaScoresCalculated> scores() {
    return published.stream()
        .filter(AreaScoresCalculated.class::isInstance)
        .map(AreaScoresCalculated.class::cast)
        .toList();
  }

  @Test
  void locationsGetCoordinatesMetricsScoresAndTheScoresGoBackToNotice() throws Exception {
    int recalculated = link.apply(event(1, found("building-a"), notFound("building-b")));

    assertThat(recalculated).isEqualTo(1); // 좌표를 찾은 위치만
    assertThat(
            one(
                "select string_agg(notice_location_id||':'||status, ',' order by notice_location_id)"
                    + " from area.notice_locations where notice_id = '"
                    + notice
                    + "'"))
        .isEqualTo("building-a:OK,building-b:FAILED");
    assertThat(
            one(
                "select count(*) from area.location_scores s join area.notice_locations l using (location_id)"
                    + " where l.notice_id = '"
                    + notice
                    + "' and s.score_kind = 'LIFE'"))
        .isEqualTo("5");

    assertThat(scores()).hasSize(1);
    AreaScoresCalculated sent = scores().getFirst();
    assertThat(sent.noticeId()).isEqualTo(notice);
    assertThat(sent.noticeVersion()).isEqualTo(1);
    // notice NoticeAreaScoreService가 받는 모양: 좌표 있는 위치만, LIVING, 0~100, 시각·규칙 버전
    assertThat(sent.scores())
        .singleElement()
        .satisfies(
            s -> {
              assertThat(s.locationId()).isEqualTo("building-a");
              assertThat(s.kind()).isEqualTo("LIVING");
              assertThat(s.score()).isBetween(0.0, 100.0);
              assertThat(s.calculatedAt()).isNotNull();
              assertThat(s.calculationVersion()).isEqualTo("2026.1");
            });
  }

  @Test
  void theSameEventTwiceDoesNotLookUpOrRecalculateAgain() throws Exception {
    answer = keyword -> new SearchOutcome.Failed(Reason.NO_KEY, null);
    link.apply(event(1, found("building-a"), notFound("building-b")));
    int searchesAfterFirst = searched.size();

    int recalculated = link.apply(event(1, found("building-a"), notFound("building-b")));

    assertThat(recalculated).isZero();
    assertThat(searched).hasSize(searchesAfterFirst);
    assertThat(scores()).hasSize(2); // 점수는 다시 보내요 (같은 값)
  }

  @Test
  void aLocationLeftOutOfANewVersionIsDeletedWithItsScores() throws Exception {
    link.apply(event(1, found("building-a"), found("building-c")));
    String c =
        one(
            "select location_id from area.notice_locations where notice_id = '"
                + notice
                + "' and notice_location_id = 'building-c'");

    link.apply(event(2, found("building-a")));

    assertThat(
            one(
                "select string_agg(notice_location_id||':'||notice_version, ',') from area.notice_locations"
                    + " where notice_id = '"
                    + notice
                    + "'"))
        .isEqualTo("building-a:2");
    assertThat(one("select count(*) from area.location_scores where location_id = '" + c + "'"))
        .isEqualTo("0");
    assertThat(scores().getLast().noticeVersion()).isEqualTo(2);
    assertThat(scores().getLast().scores())
        .extracting(AreaScoresCalculated.Score::locationId)
        .containsExactly("building-a");
  }

  @Test
  void aLocationThatFailedForASearchApiErrorIsTriedAgain() throws Exception {
    answer = keyword -> new SearchOutcome.Failed(Reason.UNAVAILABLE, "-999");
    Location jibun = new Location("site-1", "SITE", null, "부산광역시 시험구 없는동 1-1", null);
    link.apply(event(1, jibun));
    assertThat(
            one("select fail_reason from area.notice_locations where notice_id = '" + notice + "'"))
        .isEqualTo("API_ERROR");

    link.apply(event(1, jibun));

    assertThat(searched).hasSize(2); // 다시 찾아요
    assertThat(scores()).isEmpty(); // 좌표가 없으면 보낼 점수도 없어요
  }

  @Test
  void reloadingFacilitiesRecalculatesAndSendsScoresAgain() throws Exception {
    link.apply(event(3, found("building-a")));
    published.clear();

    assertThat(link.onBaseDataLoaded(AreaSource.ADDRESS_ENTRANCE)).isFalse();
    assertThat(scores()).isEmpty();

    assertThat(link.onBaseDataLoaded(AreaSource.SUBWAY_STATION)).isTrue();
    assertThat(scores())
        .filteredOn(s -> s.noticeId().equals(notice))
        .singleElement()
        .satisfies(s -> assertThat(s.noticeVersion()).isEqualTo(3));
  }

  @Test
  void failedLocationsAreListedForTheAdminScreen() {
    link.apply(event(1, notFound("building-b")));

    assertThat(link.failedLocations(1000))
        .anySatisfy(s -> assertThat(s.noticeId()).isEqualTo(notice));
  }
}
