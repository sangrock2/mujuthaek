package kr.mujuthaek.api.area.controller;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.ArgumentMatchers.isNull;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.time.OffsetDateTime;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import kr.mujuthaek.api.area.domain.AreaCriteria;
import kr.mujuthaek.api.area.domain.AreaTag;
import kr.mujuthaek.api.area.domain.Coordinate;
import kr.mujuthaek.api.area.domain.LifeCategory;
import kr.mujuthaek.api.area.domain.NearestStation;
import kr.mujuthaek.api.area.domain.SiteDetail;
import kr.mujuthaek.api.area.domain.SiteScore;
import kr.mujuthaek.api.area.service.AreaScoreService;
import kr.mujuthaek.api.area.service.AreaSiteService;
import kr.mujuthaek.api.common.exception.GlobalExceptionHandlerAccess;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

class AreaControllerTest {

  private final AreaSiteService sites = mock(AreaSiteService.class);
  private final AreaScoreService scores = mock(AreaScoreService.class);
  private final MockMvc mvc =
      MockMvcBuilders.standaloneSetup(new AreaController(sites, scores))
          .setControllerAdvice(GlobalExceptionHandlerAccess.handler())
          .build();
  private final UUID site = UUID.randomUUID();

  @Test
  void siteDetailIsPublic() throws Exception {
    when(sites.site(site))
        .thenReturn(
            Optional.of(
                new SiteDetail(
                    site,
                    37.5563,
                    126.9105,
                    false,
                    new SiteDetail.Metrics(
                        new NearestStation("망원역", 420, 7),
                        1,
                        null,
                        5,
                        300L,
                        2,
                        1,
                        900L,
                        12000,
                        null,
                        0,
                        7,
                        400L,
                        40),
                    Map.of(LifeCategory.TRANSIT, 90),
                    List.of(AreaTag.STATION, AreaTag.CONVENIENCE),
                    OffsetDateTime.parse("2026-10-18T03:00:00+09:00"))));

    mvc.perform(get("/api/v1/areas/sites/{siteId}", site))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.siteId").value(site.toString()))
        .andExpect(jsonPath("$.lat").value(37.5563))
        .andExpect(jsonPath("$.metrics.nearestStation.name").value("망원역"))
        .andExpect(jsonPath("$.metrics.busStops300m").value(5))
        .andExpect(jsonPath("$.metrics.convenienceStores300m").value(7))
        .andExpect(jsonPath("$.categoryScores.TRANSIT").value(90))
        .andExpect(jsonPath("$.tags[0]").value("STATION"))
        .andExpect(jsonPath("$.calculatedAt").value("2026-10-18T03:00:00+09:00"));

    when(sites.site(any())).thenReturn(Optional.empty());
    mvc.perform(get("/api/v1/areas/sites/{siteId}", UUID.randomUUID()))
        .andExpect(status().isNotFound())
        .andExpect(jsonPath("$.code").value("AREA_SITE_NOT_FOUND"));
  }

  @Test
  void scoreIsCalculatedPerRequestAndNeverCached() throws Exception {
    when(scores.score(
            eq(List.of(site)),
            eq(Map.of(LifeCategory.WORK, 5, LifeCategory.TRANSIT, 3)),
            eq(new Coordinate(37.5216, 126.9243))))
        .thenReturn(List.of(new SiteScore(site, 82, Map.of(LifeCategory.WORK, 90), 5000L, null)));

    mvc.perform(
            post("/api/v1/areas/score")
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    """
                    {"siteIds": ["%s"], "priorities": {"work": 5, "transit": 3},
                     "workplace": {"label": "여의도역", "lat": 37.5216, "lng": 126.9243}}"""
                        .formatted(site)))
        .andExpect(status().isOk())
        .andExpect(header().string("Cache-Control", "no-store"))
        .andExpect(jsonPath("$.items[0].siteId").value(site.toString()))
        .andExpect(jsonPath("$.items[0].total").value(82))
        .andExpect(jsonPath("$.items[0].categoryScores.WORK").value(90))
        .andExpect(jsonPath("$.items[0].commuteMeters").value(5000))
        .andExpect(jsonPath("$.items[0].commuteMinutes").isEmpty());
  }

  @Test
  void withoutPrioritiesOrWorkplaceEveryCategoryCountsTheSame() throws Exception {
    when(scores.score(eq(List.of(site)), eq(Map.of()), isNull())).thenReturn(List.of());

    mvc.perform(
            post("/api/v1/areas/score")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"siteIds\": [\"%s\"]}".formatted(site)))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.items").isEmpty());
  }

  @Test
  void badScoreRequestsAre400() throws Exception {
    mvc.perform(
            post("/api/v1/areas/score")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"siteIds\": []}"))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"));
    mvc.perform(
            post("/api/v1/areas/score")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"siteIds\": [\"%s\"], \"priorities\": {\"park\": 11}}".formatted(site)))
        .andExpect(status().isBadRequest());
    mvc.perform(
            post("/api/v1/areas/score")
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    "{\"siteIds\": [\"%s\"], \"workplace\": {\"lat\": 91, \"lng\": 0}}"
                        .formatted(site)))
        .andExpect(status().isBadRequest());
  }

  @Test
  void criteriaAreCachedForADay() throws Exception {
    when(sites.criteria())
        .thenReturn(new AreaCriteria("2026.1", List.of(), List.of(), AreaCriteria.SOURCES));

    mvc.perform(get("/api/v1/areas/criteria"))
        .andExpect(status().isOk())
        .andExpect(header().string("Cache-Control", "max-age=86400, public"))
        .andExpect(jsonPath("$.scoreVersion").value("2026.1"))
        .andExpect(jsonPath("$.sources[4].provider").value("건강보험심사평가원"));
  }
}
