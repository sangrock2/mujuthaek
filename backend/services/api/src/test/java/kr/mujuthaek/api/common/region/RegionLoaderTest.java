package kr.mujuthaek.api.common.region;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.BufferedReader;
import java.io.StringReader;
import java.nio.file.Path;
import java.time.LocalDate;
import java.util.List;
import kr.mujuthaek.api.TestDatabase;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;

/** 저장소 법정동코드표에서 뗀 짧은 자료(common/legal_dong_sample.csv)와 빌드에 들어간 실제 코드표로 확인해요. */
class RegionLoaderTest {

  private final JdbcTemplate jdbc = new JdbcTemplate(TestDatabase.dataSource());
  private final RegionLoader loader = new RegionLoader(jdbc);

  @BeforeEach
  void clean() {
    jdbc.update("delete from common.region_code_changes");
    jdbc.update("update common.regions set replaced_by = null");
    jdbc.update("delete from common.regions where level = 'SIGUNGU'");
    jdbc.update("delete from common.regions");
  }

  @Test
  void keepsOnlySidoAndSigungu_fromCommaOrTabFiles() throws Exception {
    var expected =
        List.of(
            new RegionCodeFile.Row("11", "SIDO", null, "서울특별시", "서울특별시", "서울", true),
            new RegionCodeFile.Row("11440", "SIGUNGU", "11", "마포구", "서울특별시 마포구", null, true));
    String comma =
        "법정동코드,법정동명,폐지여부\n"
            + "1100000000,서울특별시,존재\n"
            + "1144000000,서울특별시 마포구 ,존재\n" // 원본에 이름 끝 공백이 있는 줄이 있어요
            + "1144010100,서울특별시 마포구 아현동,존재\n";

    assertThat(RegionCodeFile.read(new BufferedReader(new StringReader(comma))))
        .isEqualTo(expected);
    assertThat(RegionCodeFile.read(new BufferedReader(new StringReader(comma.replace(',', '\t')))))
        .isEqualTo(expected);
  }

  @Test
  void sejongHasNoSidoLineSoTheSigunguLineMakesIt() throws Exception {
    var rows = RegionCodeFile.read(new BufferedReader(new StringReader("3611000000,세종특별자치시,존재\n")));

    assertThat(rows)
        .containsExactly(
            new RegionCodeFile.Row("36", "SIDO", null, "세종특별자치시", "세종특별자치시", "세종", true),
            new RegionCodeFile.Row("36110", "SIGUNGU", "36", "세종특별자치시", "세종특별자치시", null, true));
  }

  @Test
  void decodesCp949FilesToo() {
    byte[] cp949 = "1100000000\t서울특별시\t존재".getBytes(RegionLoader.CP949);
    byte[] utf8 = "1100000000,서울특별시,존재".getBytes(java.nio.charset.StandardCharsets.UTF_8);

    assertThat(RegionLoader.decode(cp949)).contains("서울특별시");
    assertThat(RegionLoader.decode(utf8)).contains("서울특별시");
  }

  @Test
  void loadsTheBundledRepositoryFile() throws Exception {
    RegionLoader.Bundled bundled = RegionLoader.bundled();
    loader.loadBundled();

    assertThat(bundled.fileName()).isEqualTo("legal_dong_20260929.csv");
    assertThat(bundled.baseDate()).isEqualTo(LocalDate.of(2026, 9, 29));
    assertThat(
            jdbc.queryForObject(
                "select count(*) from common.regions where level = 'SIDO' and valid",
                Integer.class))
        .isEqualTo(16);
    assertThat(names("SIDO")).contains("12:전남광주", "36:세종", "51:강원", "52:전북");
    // 2026 인천 개편: 중구·동구·서구 폐지, 제물포구·영종구·서해구·검단구 생김
    assertThat(validCodes("281")).contains("28125", "28155").doesNotContain("28110", "28140");
    assertThat(validCodes("282")).contains("28275", "28290").doesNotContain("28260");
    // 새 코드가 하나로 정해지는 것만 replaced_by
    assertThat(replacedBy("29")).isEqualTo("12");
    assertThat(replacedBy("29110")).isEqualTo("12210");
    assertThat(replacedBy("28140")).isEqualTo("28125");
    assertThat(replacedBy("28110")).isNull(); // 제물포구·영종구로 갈라짐 → 대응표에만
    assertThat(
            jdbc.queryForList(
                "select new_code from common.region_code_changes where old_code = '2811014700'",
                String.class))
        .containsExactly("2815510300");
  }

  @Test
  void loadsTheFileAndLinksReplacedCodes() throws Exception {
    int count = loader.load(sample(), LocalDate.of(2026, 7, 1));

    assertThat(count).isEqualTo(15);
    assertThat(names("SIDO"))
        .containsExactly("11:서울", "12:전남광주", "29:광주", "36:세종", "41:경기", "42:강원", "51:강원");
    assertThat(
            jdbc.queryForObject(
                "select name || '|' || full_name from common.regions where code = '41111'",
                String.class))
        .isEqualTo("수원시 장안구|경기도 수원시 장안구");
    assertThat(
            jdbc.queryForObject(
                "select name from common.regions where code = '36110'", String.class))
        .isEqualTo("세종특별자치시");
    assertThat(replacedBy("42")).isEqualTo("51");
    assertThat(replacedBy("42110")).isEqualTo("51110");
    assertThat(replacedBy("51110")).isNull();
  }

  @Test
  void loadingAgainGivesTheSameResult() throws Exception {
    loader.load(sample(), LocalDate.of(2026, 7, 1));
    loader.load(sample(), LocalDate.of(2026, 7, 1));

    assertThat(jdbc.queryForObject("select count(*) from common.regions", Integer.class))
        .isEqualTo(15);
  }

  @Test
  void sidoShortNames() {
    assertThat(RegionCodeFile.shortName("전북특별자치도")).isEqualTo("전북");
    assertThat(RegionCodeFile.shortName("전라남도")).isEqualTo("전남");
    assertThat(RegionCodeFile.shortName("경상북도")).isEqualTo("경북");
    assertThat(RegionCodeFile.shortName("제주특별자치도")).isEqualTo("제주");
    assertThat(RegionCodeFile.shortName("전남광주통합특별시")).isEqualTo("전남광주");
    assertThat(RegionCodeFile.shortName("광주광역시")).isEqualTo("광주");
  }

  private List<String> names(String level) {
    return jdbc.queryForList(
        "select code || ':' || short_name from common.regions where level = ? order by code",
        String.class,
        level);
  }

  private List<String> validCodes(String prefix) {
    return jdbc.queryForList(
        "select code from common.regions where level = 'SIGUNGU' and valid and code like ? order by code",
        String.class,
        prefix + "%");
  }

  private String replacedBy(String code) {
    return jdbc.queryForObject(
        "select replaced_by from common.regions where code = ?", String.class, code);
  }

  private static Path sample() throws Exception {
    return Path.of(
        RegionLoaderTest.class
            .getClassLoader()
            .getResource("common/legal_dong_sample.csv")
            .toURI());
  }
}
