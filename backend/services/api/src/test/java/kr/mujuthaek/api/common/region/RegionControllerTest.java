package kr.mujuthaek.api.common.region;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.nio.file.Path;
import java.time.LocalDate;
import kr.mujuthaek.api.TestDatabase;
import kr.mujuthaek.api.common.exception.GlobalExceptionHandlerAccess;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

class RegionControllerTest {

  private final JdbcTemplate jdbc = new JdbcTemplate(TestDatabase.dataSource());
  private final RegionQueryService service = new RegionQueryService(jdbc);
  private final MockMvc mvc =
      MockMvcBuilders.standaloneSetup(new RegionController(service))
          .setControllerAdvice(GlobalExceptionHandlerAccess.handler())
          .build();

  @BeforeEach
  void load() throws Exception {
    jdbc.update("delete from common.region_code_changes");
    jdbc.update("update common.regions set replaced_by = null");
    jdbc.update("delete from common.regions where level = 'SIGUNGU'");
    jdbc.update("delete from common.regions");
    Path sample =
        Path.of(getClass().getClassLoader().getResource("common/legal_dong_sample.csv").toURI());
    new RegionLoader(jdbc).load(sample, LocalDate.of(2026, 7, 1));
  }

  @Test
  void listsValidSidosWithTheirSigungus() throws Exception {
    mvc.perform(get("/api/v1/regions"))
        .andExpect(status().isOk())
        .andExpect(header().string("Cache-Control", "max-age=86400, public"))
        .andExpect(header().exists("ETag"))
        .andExpect(jsonPath("$.baseDate").value("2026-07-01"))
        .andExpect(jsonPath("$.sidos.length()").value(5)) // 폐지된 광주(29)·강원도(42)는 빠져요
        .andExpect(jsonPath("$.sidos[0].code").value("11"))
        .andExpect(jsonPath("$.sidos[0].name").value("서울특별시"))
        .andExpect(jsonPath("$.sidos[0].shortName").value("서울"))
        .andExpect(jsonPath("$.sidos[0].sigungus[0].code").value("11440"))
        .andExpect(jsonPath("$.sidos[0].sigungus[0].name").value("마포구"));
  }

  @Test
  void sameEtagMeansNotModified() throws Exception {
    String etag = mvc.perform(get("/api/v1/regions")).andReturn().getResponse().getHeader("ETag");

    mvc.perform(get("/api/v1/regions").header("If-None-Match", etag))
        .andExpect(status().isNotModified());
  }

  @Test
  void oldCodesPointToTheirReplacement() throws Exception {
    mvc.perform(get("/api/v1/regions/42110"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.valid").value(false))
        .andExpect(jsonPath("$.replacedBy").value("51110"))
        .andExpect(jsonPath("$.name").value("춘천시"));
  }

  @Test
  void unknownAndMalformedCodes() throws Exception {
    mvc.perform(get("/api/v1/regions/99999"))
        .andExpect(status().isNotFound())
        .andExpect(jsonPath("$.code").value("NOT_FOUND"));
    mvc.perform(get("/api/v1/regions/1144"))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"));
  }

  @Test
  void displayNameJoinsSidoShortNameAndSigungu() {
    assertThat(service.displayName("11440")).isEqualTo("서울 마포구");
    assertThat(service.displayName("41")).isEqualTo("경기");
    assertThat(service.displayName("00000")).isNull();
  }
}
