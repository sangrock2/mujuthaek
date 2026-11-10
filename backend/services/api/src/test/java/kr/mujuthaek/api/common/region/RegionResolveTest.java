package kr.mujuthaek.api.common.region;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import kr.mujuthaek.api.TestDatabase;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;

/** 빌드에 들어간 실제 법정동코드표를 넣고 이름 → 코드를 확인해요. */
class RegionResolveTest {

  private static final JdbcTemplate jdbc = new JdbcTemplate(TestDatabase.dataSource());
  private static final RegionQueryService service = new RegionQueryService(jdbc);

  @BeforeAll
  static void load() throws Exception {
    jdbc.update("delete from common.region_code_changes");
    jdbc.update("update common.regions set replaced_by = null");
    jdbc.update("delete from common.regions where level = 'SIGUNGU'");
    jdbc.update("delete from common.regions");
    new RegionLoader(jdbc).loadBundled();
  }

  @Test
  void sidoNamesAndAliases() {
    assertThat(service.resolve("서울특별시", null).code()).isEqualTo("11");
    assertThat(service.resolve("서울시", null).code()).isEqualTo("11");
    assertThat(service.resolve("서울", null).code()).isEqualTo("11");
    assertThat(service.resolve("강원도", null).code()).isEqualTo("51"); // 폐지된 이름 → 지금 코드
    assertThat(service.resolve("광주광역시", null).code()).isEqualTo("12");
    assertThat(service.resolve("세종특별자치시", null).code()).isEqualTo("36");
  }

  @Test
  void generalDistrictsWithOrWithoutTheirCity() {
    assertThat(service.resolve("경기도", "수원시 장안구").code()).isEqualTo("41111");
    assertThat(service.resolve("경기도", "장안구").code()).isEqualTo("41111");
    assertThat(service.resolve(null, "장안구").code()).isEqualTo("41111");
    assertThat(service.resolve("경기도", "화성시 병점구").code()).isEqualTo("41595");
  }

  @Test
  void sameNameDistrictsNeedTheSido() {
    RegionQueryService.RegionMatch junggu = service.resolve(null, "중구");

    assertThat(junggu.code()).isNull();
    assertThat(junggu.candidates()).contains("11140", "26110", "27110", "30140", "31110");
    assertThat(service.resolve("서울특별시", "중구").code()).isEqualTo("11140");
    assertThat(service.resolve("대전광역시", "중구").code()).isEqualTo("30140");
  }

  @Test
  void oldNamesGoToTheirCurrentCode() {
    assertThat(service.resolve("광주광역시", "동구").code()).isEqualTo("12210");
    assertThat(service.resolve("강원도", "춘천시").code()).isEqualTo("51110");
    // 인천 중구는 제물포구·영종구로 갈라져 하나로 못 정하고 둘을 후보로
    RegionQueryService.RegionMatch incheonJunggu = service.resolve("인천광역시", "중구");
    assertThat(incheonJunggu.code()).isNull();
    assertThat(incheonJunggu.candidates()).containsExactly("28125", "28155");
    assertThat(service.resolve("인천광역시", "동구").code()).isEqualTo("28125");
  }

  @Test
  void unknownNames() {
    assertThat(service.resolve("서울특별시", "없는구").candidates()).isEmpty();
    assertThat(service.resolve("없는도", "중구").code()).isNull();
  }

  @Test
  void legalDongCodesToCurrent() {
    assertThat(service.toCurrent("2811014700")).containsExactly("2815510300");
    assertThat(service.toCurrent("1144010100")).containsExactly("1144010100"); // 그대로 있는 코드
    assertThat(service.toCurrent("1165011300")).containsExactly("1165011300"); // 대응을 모르는 폐지 코드는 그대로
    assertThat(service.toCurrent("123")).isEmpty();
  }

  @Test
  void resolvesEverySigunguInRealNoticeAddresses() throws Exception {
    // 실제 공고 주소 정답 케이스(area 주소 → 좌표)의 시도·시군구 이름과 기대 코드
    List<String> wrong = new ArrayList<>();
    try (BufferedReader reader =
        new BufferedReader(
            new InputStreamReader(
                getClass().getClassLoader().getResourceAsStream("common/region_name_cases.csv"),
                StandardCharsets.UTF_8))) {
      reader.readLine();
      String line;
      while ((line = reader.readLine()) != null) {
        String[] c = line.split(",", -1);
        String code = service.resolve(c[0].isEmpty() ? null : c[0], c[1]).code();
        if (!c[2].equals(code)) {
          wrong.add(line + " → " + code);
        }
      }
    }
    assertThat(wrong).isEmpty();
  }
}
