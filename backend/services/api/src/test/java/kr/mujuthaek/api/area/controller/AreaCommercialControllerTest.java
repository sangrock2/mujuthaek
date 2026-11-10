package kr.mujuthaek.api.area.controller;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.time.OffsetDateTime;
import java.util.LinkedHashMap;
import java.util.Optional;
import java.util.UUID;
import kr.mujuthaek.api.area.domain.CommercialIndustry;
import kr.mujuthaek.api.area.domain.CommercialScore;
import kr.mujuthaek.api.area.domain.NearestStation;
import kr.mujuthaek.api.area.service.AreaCommercialService;
import kr.mujuthaek.api.common.exception.GlobalExceptionHandlerAccess;
import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

class AreaCommercialControllerTest {

  private final AreaCommercialService service = mock(AreaCommercialService.class);
  private final MockMvc mvc =
      MockMvcBuilders.standaloneSetup(new AreaCommercialController(service))
          .setControllerAdvice(GlobalExceptionHandlerAccess.handler())
          .build();

  @Test
  void returnsTheApiDocShape() throws Exception {
    UUID site = UUID.randomUUID();
    var scores = new LinkedHashMap<String, Integer>();
    scores.put("DENSITY", 78);
    scores.put("COMPETITION", 55);
    scores.put("TRANSIT", 92);
    when(service.score(eq(site), eq("CAFE")))
        .thenReturn(
            Optional.of(
                new CommercialScore(
                    site,
                    186,
                    12L,
                    CommercialIndustry.CAFE,
                    new NearestStation("○○역", 380, 5),
                    null,
                    scores,
                    75,
                    OffsetDateTime.parse("2026-10-21T03:00:00+09:00"))));

    mvc.perform(get("/api/v1/areas/commercial/{siteId}", site).param("industry", "CAFE"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.siteId").value(site.toString()))
        .andExpect(jsonPath("$.stores300m").value(186))
        .andExpect(jsonPath("$.sameIndustry300m").value(12))
        .andExpect(jsonPath("$.industryGroup").value("CAFE"))
        .andExpect(jsonPath("$.nearestStation.name").value("○○역"))
        .andExpect(jsonPath("$.nearestStation.meters").value(380))
        .andExpect(jsonPath("$.nearestStation.walkMinutes").value(5))
        .andExpect(jsonPath("$.scores.COMPETITION").value(55))
        .andExpect(jsonPath("$.score").value(75))
        .andExpect(jsonPath("$.calculatedAt").value("2026-10-21T03:00:00+09:00"));
  }

  @Test
  void unknownSiteIs404() throws Exception {
    when(service.score(any(), any())).thenReturn(Optional.empty());

    mvc.perform(get("/api/v1/areas/commercial/{siteId}", UUID.randomUUID()))
        .andExpect(status().isNotFound())
        .andExpect(jsonPath("$.code").value("AREA_SITE_NOT_FOUND"));
    mvc.perform(get("/api/v1/areas/commercial/not-a-uuid")).andExpect(status().isBadRequest());
  }
}
