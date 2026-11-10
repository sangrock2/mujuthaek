package kr.mujuthaek.api.area.repository;

import static kr.mujuthaek.api.area.AreaTestDatabase.exec;
import static kr.mujuthaek.api.area.AreaTestDatabase.one;
import static org.assertj.core.api.Assertions.assertThat;

import java.util.UUID;
import kr.mujuthaek.api.area.AreaTestDatabase;
import kr.mujuthaek.api.area.domain.Coordinate;
import kr.mujuthaek.api.area.domain.GeocodeResult;
import kr.mujuthaek.api.area.domain.GeocodeResult.FailReason;
import kr.mujuthaek.api.area.domain.GeocodeResult.Method;
import kr.mujuthaek.api.area.domain.GeocodeResult.Status;
import kr.mujuthaek.api.area.domain.NoticeLocation;
import kr.mujuthaek.api.area.domain.StoredLocation;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;

class PostgresNoticeLocationsTest {

  private final PostgresNoticeLocations locations =
      new PostgresNoticeLocations(AreaTestDatabase.dataSource());
  private final UUID notice = UUID.randomUUID();

  @AfterEach
  void clean() throws Exception {
    exec("delete from area.notice_locations where notice_id = '" + notice + "'");
  }

  private NoticeLocation location(int version, String address) {
    return new NoticeLocation(notice, version, "building-a", "BUILDING", address, "2611010100");
  }

  private static GeocodeResult ok(Method method) {
    return new GeocodeResult(
        Status.OK, method, new Coordinate(35.1, 129.04), "2611010100", "26110", "x", null, true);
  }

  @Test
  void savingAgainKeepsTheAreaLocationIdAndReplacesTheRest() throws Exception {
    UUID first = locations.save(location(1, "초량상로 1-2"), "키1", ok(Method.FILE));
    UUID again =
        locations.save(
            location(2, "어딘가 9"), "키2", GeocodeResult.failed(FailReason.NOT_FOUND, null));

    assertThat(again).isEqualTo(first);
    assertThat(
            one(
                "select notice_version||'|'||address_text||'|'||address_key||'|'||status||'|'"
                    + "||coalesce(method,'-')||'|'||fail_reason||'|'||(geom is null)"
                    + " from area.notice_locations where location_id = '"
                    + first
                    + "'"))
        .isEqualTo("2|어딘가 9|키2|FAILED|-|NOT_FOUND|true");
  }

  @Test
  void storesTheCoordinateAndFlags() throws Exception {
    UUID id = locations.save(location(1, "초량상로 1-2"), "키1", ok(Method.SEARCH_API));

    assertThat(
            one(
                "select round(st_y(geom::geometry)::numeric, 2)||','||round(st_x(geom::geometry)::numeric, 2)"
                    + "||'|'||method||'|'||bjd_code_given||'|'||bjd_code_found||'|'||region_mismatch"
                    + " from area.notice_locations where location_id = '"
                    + id
                    + "'"))
        .isEqualTo("35.10,129.04|SEARCH_API|2611010100|2611010100|true");
  }

  @Test
  void onlyAnExactCoordinateIsReused() {
    String key = "재사용 " + notice;
    String bjd = "2611010100"; // location()이 주는 법정동코드
    assertThat(locations.reusable(key, bjd)).isEmpty();

    locations.save(
        location(1, "범위만"),
        key,
        GeocodeResult.approx(new Coordinate(35.0, 129.0), "2611010100", "26110"));
    assertThat(locations.reusable(key, bjd)).isEmpty(); // 대략 위치는 다시 찾아요

    locations.save(location(1, "초량상로 1-2"), key, ok(Method.COORD_API));
    GeocodeResult reused = locations.reusable(key, bjd).orElseThrow();
    assertThat(reused.method()).isEqualTo(Method.COORD_API);
    assertThat(reused.coordinate().lat()).isEqualTo(35.1);
    assertThat(reused.bjdCodeFound()).isEqualTo("2611010100");
    assertThat(reused.regionMismatch()).isTrue();
    assertThat(locations.reusable(" ", bjd)).isEmpty();
  }

  @Test
  void theSameAddressTextWithAnotherLegalDongCodeIsNotReused() {
    // 2026-11-10 코드 검토: 「중앙로 7」처럼 시군구 없는 주소는 법정동코드로 시군구를 좁혀 찾아서, 주소 글자만 같으면 다른 도시 좌표를 썼음
    String key = "중앙로 7 " + notice;
    locations.save(location(1, "중앙로 7"), key, ok(Method.SEARCH_API));

    assertThat(locations.reusable(key, "2611010100")).isPresent();
    assertThat(locations.reusable(key, "4111110100")).isEmpty();
    assertThat(locations.reusable(key, null)).isEmpty();

    locations.save(at("c", "중앙로 7"), key, ok(Method.SEARCH_API)); // 코드 없이 찾은 것은 코드 없는 위치만 다시 써요
    assertThat(locations.reusable(key, null)).isPresent();
  }

  private NoticeLocation at(String id, String address) {
    return new NoticeLocation(notice, 1, id, "COMPLEX", address, null);
  }

  @Test
  void readsTheLocationsOfANoticeAndDeletesTheOnesThatDisappeared() throws Exception {
    UUID a = locations.save(at("a", "주소 1"), "키a", ok(Method.FILE));
    UUID b =
        locations.save(at("b", "주소 2"), "키b", GeocodeResult.failed(FailReason.NOT_FOUND, null));
    exec(
        "insert into area.location_metrics (location_id, metric, value) values ('"
            + a
            + "', 'store_count_300m', 3)");

    var stored = locations.ofNotice(notice);
    assertThat(stored).extracting(StoredLocation::noticeLocationId).containsExactly("a", "b");
    assertThat(stored.get(0).coordinate().lat()).isEqualTo(35.1);
    assertThat(stored.get(1).coordinate()).isNull();
    assertThat(stored.get(1).failReason()).isEqualTo(FailReason.NOT_FOUND);
    assertThat(locations.failed(100)).extracting(StoredLocation::locationId).contains(b);
    assertThat(locations.withCoordinates())
        .extracting(StoredLocation::locationId)
        .contains(a)
        .doesNotContain(b);

    // 새 버전에 a가 빠지면 a와 그 지표가 같이 지워져요
    assertThat(locations.deleteMissing(notice, java.util.List.of("b"))).isEqualTo(1);
    assertThat(locations.ofNotice(notice))
        .extracting(StoredLocation::noticeLocationId)
        .containsExactly("b");
    assertThat(one("select count(*) from area.location_metrics where location_id = '" + a + "'"))
        .isEqualTo("0");

    locations.touchVersion(b, 7);
    assertThat(locations.ofNotice(notice).getFirst().noticeVersion()).isEqualTo(7);
  }
}
