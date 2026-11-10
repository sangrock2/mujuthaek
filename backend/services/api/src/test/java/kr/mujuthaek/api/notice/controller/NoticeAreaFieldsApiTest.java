package kr.mujuthaek.api.notice.controller;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.util.UUID;
import kr.mujuthaek.api.notice.NoticeApiFixture;
import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.MockMvc;

/**
 * 공고 목록·상세·지도에 붙는 area 값 (8단계). area 값은 시험 DB의 area 표에 직접 넣어요(연결 PR이 계산해 두는 값). 시험 좌표는 동해 바다
 * 위(132.x, 38.x)예요.
 */
class NoticeAreaFieldsApiTest {

  private final NoticeApiFixture f = new NoticeApiFixture();
  private final MockMvc mvc = f.mvc(new NoticeController(f.queries));

  /** 공고의 위치 building-a(계약 예시 공고의 위치 ID)에 area 좌표·지표·점수를 넣고 area 위치 ID를 돌려줘요. */
  static UUID areaSite(NoticeApiFixture f, UUID notice, double lng, double lat) {
    UUID site =
        f.jdbc.queryForObject(
            "insert into area.notice_locations (notice_id, notice_location_id, notice_version, kind,"
                + " address_text, geom, status, method) values (?, 'building-a', 1, 'BUILDING', '주소',"
                + " st_makepoint(?, ?)::geography, 'OK', 'FILE') returning location_id",
            UUID.class,
            notice,
            lng,
            lat);
    f.jdbc.update(
        "insert into area.location_metrics (location_id, metric, value) values (?, 'station_nearest_m', 300),"
            + " (?, 'convenience_store_count_300m', 4)",
        site,
        site);
    f.jdbc.update(
        "insert into area.location_scores (location_id, score_kind, category, score, score_version)"
            + " values (?, 'LIFE', 'TRANSIT', 90, '2026.1'), (?, 'LIFE', 'PARK', 61, '2026.1')",
        site,
        site);
    return site;
  }

  @Test
  void listItemsCarryTheRepresentativeSite() throws Exception {
    UUID withArea = f.notice(p -> {});
    UUID withoutArea = f.notice(p -> {});
    areaSite(f, withArea, 132.10, 38.10);

    mvc.perform(get("/api/v1/notices").param("providers", f.provider))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.items[?(@.id == '%s')].lat".formatted(withArea)).value(38.10))
        .andExpect(jsonPath("$.items[?(@.id == '%s')].siteCount".formatted(withArea)).value(1))
        .andExpect(jsonPath("$.items[?(@.id == '%s')].areaScore".formatted(withArea)).value(76))
        .andExpect(
            jsonPath("$.items[?(@.id == '%s')].tags[0]".formatted(withArea)).value("STATION"))
        .andExpect(jsonPath("$.items[?(@.id == '%s')].siteCount".formatted(withoutArea)).value(0))
        .andExpect(
            jsonPath("$.items[?(@.id == '%s')].lat".formatted(withoutArea)).value((Object) null));
  }

  @Test
  void detailSitesCarryTheAreaSiteId() throws Exception {
    UUID notice = f.notice(p -> {});
    UUID site = areaSite(f, notice, 132.20, 38.20);

    mvc.perform(get("/api/v1/notices/{id}", notice))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.sites[0].id").value("building-a"))
        .andExpect(jsonPath("$.sites[0].siteId").value(site.toString()))
        .andExpect(jsonPath("$.sites[0].lat").value(38.20))
        .andExpect(jsonPath("$.sites[0].tags[1]").value("CONVENIENCE"));
  }

  @Test
  void mapGivesPinsInsideTheBounds() throws Exception {
    UUID inside = f.notice(p -> {});
    UUID outside = f.notice(p -> {});
    areaSite(f, inside, 132.30, 38.30);
    areaSite(f, outside, 132.90, 38.90);

    mvc.perform(
            get("/api/v1/notices/map")
                .param("swLat", "38.25")
                .param("swLng", "132.25")
                .param("neLat", "38.35")
                .param("neLng", "132.35")
                .param("providers", f.provider))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.clusters").isEmpty())
        .andExpect(jsonPath("$.pins.length()").value(1))
        .andExpect(jsonPath("$.pins[0].id").value(inside.toString()))
        .andExpect(jsonPath("$.pins[0].lat").value(38.30));

    mvc.perform(
            get("/api/v1/notices/map")
                .param("swLat", "38.35")
                .param("swLng", "132.25")
                .param("neLat", "38.25")
                .param("neLng", "132.35"))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"));
  }
}
