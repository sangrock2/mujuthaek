package kr.mujuthaek.api.area.service;

import static kr.mujuthaek.api.area.AreaTestDatabase.exec;
import static kr.mujuthaek.api.area.AreaTestDatabase.one;
import static org.assertj.core.api.Assertions.assertThat;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.function.Function;
import kr.mujuthaek.api.area.AreaTestDatabase;
import kr.mujuthaek.api.area.domain.GeocodeResult.Method;
import kr.mujuthaek.api.area.domain.GeocodeResult.Status;
import kr.mujuthaek.api.area.domain.NoticeLocation;
import kr.mujuthaek.api.area.geocode.CoordOutcome;
import kr.mujuthaek.api.area.geocode.JusoResult;
import kr.mujuthaek.api.area.geocode.SearchOutcome;
import kr.mujuthaek.api.area.geocode.SearchOutcome.Found;
import kr.mujuthaek.api.area.geocode.SearchOutcome.NotFound;
import kr.mujuthaek.api.area.geocode.SearchOutcome.Reason;
import kr.mujuthaek.api.area.repository.PostgresAddressPointLookup;
import kr.mujuthaek.api.area.repository.PostgresLegalDongCentroid;
import kr.mujuthaek.api.area.repository.PostgresNoticeLocations;
import kr.mujuthaek.api.area.repository.PostgresRegionBoundaryCheck;
import kr.mujuthaek.api.area.repository.PostgresUtmkTransform;
import kr.mujuthaek.api.common.region.RegionLoader;
import kr.mujuthaek.api.common.region.RegionQueryService;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;

/**
 * 공고 위치 → 좌표 → 저장 끝까지 (계획 18번). 지역 코드표는 저장소의 실제 법정동코드표를 넣고(주소의 실제 시도·시군구 이름으로 찾게), 사전은 정답 케이스에서 만들어
 * 넣어요. 검색 API는 가짜예요. 시험 사전 줄은 load_scope 98이라 끝나면 지워요.
 */
class NoticeLocationServiceTest {

  private final List<String> searched = new ArrayList<>();
  private Function<String, SearchOutcome> answer = keyword -> new NotFound();
  private final NoticeLocationService service =
      new NoticeLocationService(
          new AddressLocator(
              new PostgresAddressPointLookup(AreaTestDatabase.dataSource()),
              keyword -> {
                searched.add(keyword);
                return answer.apply(keyword);
              },
              building -> new CoordOutcome.Failed(Reason.NO_KEY, null),
              new PostgresUtmkTransform(AreaTestDatabase.dataSource()),
              new PostgresLegalDongCentroid(AreaTestDatabase.dataSource()),
              new PostgresRegionBoundaryCheck(AreaTestDatabase.dataSource()),
              new RegionQueryService(new JdbcTemplate(AreaTestDatabase.dataSource()))),
          new PostgresNoticeLocations(AreaTestDatabase.dataSource()));

  @BeforeAll
  static void realRegionCodes() throws Exception {
    new RegionLoader(new JdbcTemplate(AreaTestDatabase.dataSource())).loadBundled();
  }

  @AfterEach
  void clean() throws Exception {
    exec("delete from area.address_points where load_scope = '98'");
    exec("delete from area.notice_locations where notice_location_id like 'case-%'");
    exec("delete from common.region_code_changes where old_code = '2811099900'");
  }

  @Test
  void answerCasesWithRoadAddressesAreFoundEndToEnd() throws Exception {
    List<List<String>> cases = roadCasesWithAnswers();
    for (List<String> c : cases) {
      // address_id = 시군구5 + 읍면동3 + 도로명번호7 + 지하1 + 본번5 + 부번5
      String id = c.get(13);
      exec(
          "insert into area.address_points (address_id, load_scope, bjd_code, sigungu_code, road_code, road_name,"
              + " underground, bldg_main, bldg_sub, geom, data_date) values ('"
              + id
              + "', '98', '"
              + id.substring(0, 8)
              + "00', '"
              + id.substring(0, 5)
              + "', '"
              + id.substring(0, 12)
              + "', '"
              + c.get(4)
              + "', "
              + ("true".equalsIgnoreCase(c.get(5)) || "1".equals(c.get(5)) ? 1 : 0)
              + ", "
              + c.get(6)
              + ", "
              + (c.get(7).isEmpty() ? "0" : c.get(7))
              + ", st_makepoint(127, 37)::geography, date '2026-09-30')"
              + " on conflict (address_id) do update set load_scope = '98'");
      // 시험 좌표(127, 37)가 실제 시군구 경계 밖이라 경계 검사에 걸리지 않게 그 시군구 경계는 빼요
      exec(
          "delete from area.region_boundaries where level = 'SIG' and code = '"
              + id.substring(0, 5)
              + "'");
    }
    exec(
        "insert into area.road_names select distinct sigungu_code, road_name from area.address_points"
            + " where load_scope = '98' on conflict do nothing");

    int found = 0;
    for (int i = 0; i < cases.size(); i++) {
      List<String> c = cases.get(i);
      var located = service.locate(location("case-" + i, c.get(0), null));
      if (located.result().status() == Status.OK
          && located.result().method() == Method.FILE
          && (located.reused() || c.get(13).equals(located.result().addressId()))) {
        found++;
      }
    }

    assertThat(cases).hasSizeGreaterThan(100);
    assertThat(found).isEqualTo(cases.size()); // 주소 정리 → 이름으로 시군구 → 사전, 모두 정답 주소
    assertThat(searched).isEmpty();
  }

  @Test
  void theSameAddressTwiceIsLookedUpOnce() throws Exception {
    dictionary("26530", "모라시험로", 7, "26530101");
    answer = keyword -> new Found(List.of(juso("2653010100", "모라시험로", "7")), 1);

    var first = service.locate(location("case-a", "부산광역시 사상구 모라동 656-6", null));
    var second = service.locate(location("case-b", "부산광역시  사상구 모라동 656-6", null));

    assertThat(first.result().method()).isEqualTo(Method.SEARCH_API);
    assertThat(second.reused()).isTrue();
    assertThat(second.result().coordinate()).isEqualTo(first.result().coordinate());
    assertThat(searched).hasSize(1); // 두 번째는 검색 API를 부르지 않아요
    assertThat(first.locationId()).isNotEqualTo(second.locationId()); // 위치는 따로 저장
    assertThat(
            one(
                "select count(*) from area.notice_locations where notice_location_id in ('case-a', 'case-b')"))
        .isEqualTo("2");
  }

  @Test
  void anOldCodeSplitByThe2026ReformIsResolvedByTheAddressName() throws Exception {
    // 예전 인천 중구 코드가 제물포구·영종구 둘로 갈라졌으면 코드만으로는 어느 쪽인지 몰라요 → 주소의 「영종구」로
    exec(
        "insert into common.region_code_changes values ('2811099900', '2812599900', date '2026-09-29'),"
            + " ('2811099900', '2815599900', date '2026-09-29')");
    dictionary("28155", "영종시험로", 7, "28155101");

    var located = service.locate(location("case-c", "인천광역시 영종구 영종시험로 7", "2811099900"));

    assertThat(located.result().status()).isEqualTo(Status.OK);
    assertThat(located.result().sigunguCode()).isEqualTo("28155");
  }

  private static NoticeLocation location(String id, String address, String bjd) {
    return new NoticeLocation(UUID.randomUUID(), 1, id, "COMPLEX", address, bjd);
  }

  private static JusoResult juso(String admCd, String road, String main) {
    return new JusoResult(admCd, road, "0", main, "0", null, null, null, null, null, null, null);
  }

  private static void dictionary(String sigungu, String road, int main, String emd8)
      throws Exception {
    exec(
        "insert into area.address_points (address_id, load_scope, bjd_code, sigungu_code, road_code, road_name,"
            + " underground, bldg_main, bldg_sub, geom, data_date) values ('"
            + (emd8 + "9999999" + "0" + String.format("%05d", main) + "00000")
            + "', '98', '"
            + emd8
            + "00', '"
            + sigungu
            + "', '"
            + sigungu
            + "9999999', '"
            + road
            + "', 0, "
            + main
            + ", 0, st_makepoint(127, 37)::geography, date '2026-09-30')");
    exec("delete from area.region_boundaries where level = 'SIG' and code = '" + sigungu + "'");
  }

  /** 정답 케이스 중 도로명 주소이고 정답 주소 ID가 있는 줄. */
  private static List<List<String>> roadCasesWithAnswers() throws Exception {
    List<List<String>> out = new ArrayList<>();
    try (var in =
        new BufferedReader(
            new InputStreamReader(
                NoticeLocationServiceTest.class.getResourceAsStream("/area/geocode/cases.csv"),
                StandardCharsets.UTF_8))) {
      in.readLine();
      String line;
      while ((line = in.readLine()) != null) {
        List<String> f = csv(line);
        if ("ROAD".equals(f.get(1)) && !f.get(13).isEmpty()) {
          out.add(f);
        }
      }
    }
    return out;
  }

  private static List<String> csv(String line) {
    List<String> out = new ArrayList<>();
    StringBuilder cur = new StringBuilder();
    boolean quoted = false;
    for (int i = 0; i < line.length(); i++) {
      char ch = line.charAt(i);
      if (quoted) {
        if (ch == '"' && i + 1 < line.length() && line.charAt(i + 1) == '"') {
          cur.append('"');
          i++;
        } else if (ch == '"') {
          quoted = false;
        } else {
          cur.append(ch);
        }
      } else if (ch == '"') {
        quoted = true;
      } else if (ch == ',') {
        out.add(cur.toString());
        cur.setLength(0);
      } else {
        cur.append(ch);
      }
    }
    out.add(cur.toString());
    return out;
  }
}
