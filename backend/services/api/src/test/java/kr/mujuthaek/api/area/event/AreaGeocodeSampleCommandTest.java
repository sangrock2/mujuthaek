package kr.mujuthaek.api.area.event;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import kr.mujuthaek.api.area.AreaTestDatabase;
import kr.mujuthaek.api.area.geocode.CoordOutcome;
import kr.mujuthaek.api.area.geocode.SearchOutcome;
import kr.mujuthaek.api.area.repository.PostgresAddressPointLookup;
import kr.mujuthaek.api.area.repository.PostgresLegalDongCentroid;
import kr.mujuthaek.api.area.repository.PostgresRegionBoundaryCheck;
import kr.mujuthaek.api.area.repository.PostgresUtmkTransform;
import kr.mujuthaek.api.area.service.AddressLocator;
import kr.mujuthaek.api.common.region.RegionQueryService;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;

class AreaGeocodeSampleCommandTest {

  @Test
  void readsQuotedFields() {
    assertThat(AreaGeocodeSampleCommand.fields("\"가,나\",ROAD,\"따옴\"\"표\",,끝"))
        .containsExactly("가,나", "ROAD", "따옴\"표", "", "끝");
  }

  @Test
  void runsEveryLineOfTheSample() throws Exception {
    var locator =
        new AddressLocator(
            new PostgresAddressPointLookup(AreaTestDatabase.dataSource()),
            keyword -> new SearchOutcome.NotFound(),
            building -> new CoordOutcome.NotFound(),
            new PostgresUtmkTransform(AreaTestDatabase.dataSource()),
            new PostgresLegalDongCentroid(AreaTestDatabase.dataSource()),
            new PostgresRegionBoundaryCheck(AreaTestDatabase.dataSource()),
            new RegionQueryService(new JdbcTemplate(AreaTestDatabase.dataSource())));
    String csv =
        """
        address,kind,sido,sigungu,road_name,underground,bldg_main,bldg_sub,dong,san,jibun_main,jibun_sub,sigungu_code,address_id
        주소 별도 안내,UNKNOWN,,,,,,,,,,,,

        "없는시 없는로 1(동)",ROAD,,,없는로,0,1,0,,,,,,99999999999999999999999999
        """;

    String md =
        AreaGeocodeSampleCommand.run(
            new ByteArrayInputStream(csv.getBytes(StandardCharsets.UTF_8)), locator);

    assertThat(md).contains("| 2 | 0 | 0 | 2 |"); // 빈 줄은 건너뜀
    assertThat(md).contains("- PARSE_FAILED 1");
  }

  @Test
  void theBundledAnswerCasesAreWhereTheCommandLooksFor() {
    // 테스트는 services/api에서 돌아요 (bootRun과 같은 곳)
    assertThat(Files.exists(Path.of(AreaGeocodeSampleCommand.BUNDLED_CASES))).isTrue();
  }
}
