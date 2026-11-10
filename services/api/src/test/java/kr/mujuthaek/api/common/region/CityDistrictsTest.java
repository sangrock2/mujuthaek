package kr.mujuthaek.api.common.region;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;
import org.junit.jupiter.api.Test;

/** 일반구가 있는 시 목록이 법정동코드표(빌드 리소스 common/regions)와 맞는지, 시·구 판정이 맞는지. */
class CityDistrictsTest {

  @Test
  void theCityListMatchesTheLegalDongCodeTable() throws Exception {
    // 지금 있는 시군구 중, 같은 앞 4자리의 지금 있는 시군구가 「그 시 이름 + 구 이름」인 시만 일반구가 있는 시예요(영동군 다음 증평군은 아님)
    Map<String, String> sigungu = new HashMap<>();
    try (var in = getClass().getResourceAsStream("/common/regions/legal_dong_20260929.csv");
        var reader = new BufferedReader(new InputStreamReader(in, StandardCharsets.UTF_8))) {
      reader.readLine();
      for (String line; (line = reader.readLine()) != null; ) {
        String[] cells = line.split(",");
        if (cells.length >= 3
            && "존재".equals(cells[2].strip())
            && cells[0].endsWith("00000")
            && !cells[0].startsWith("000", 2)) {
          sigungu.put(cells[0].substring(0, 5), cells[1].strip());
        }
      }
    }
    Set<String> cities = new TreeSet<>();
    sigungu.forEach(
        (code, name) -> {
          if (code.charAt(4) != '0') {
            String city = code.substring(0, 4) + "0";
            String cityName = sigungu.get(city);
            if (cityName != null && name.startsWith(cityName + " ")) {
              cities.add(city);
            }
          }
        });
    assertThat(cities).isEqualTo(new TreeSet<>(CityDistricts.CITIES));
  }

  @Test
  void districtsBelongOnlyToTheirListedCity() {
    assertThat(CityDistricts.inCity("41110", "41111")).isTrue();
    assertThat(CityDistricts.inCity("4111000000", "4111712300")).isTrue();
    assertThat(CityDistricts.inCity("41110", "41110")).isFalse(); // 시 자신은 구가 아님
    assertThat(CityDistricts.inCity("43740", "43745")).isFalse(); // 영동군 다음 증평군
    assertThat(CityDistricts.cityOf("41117")).isEqualTo("41110");
    assertThat(CityDistricts.cityOf("43745")).isNull();
    assertThat(CityDistricts.cityOf("41110")).isNull();
    assertThat(CityDistricts.isCity("4111000000")).isTrue();
    assertThat(CityDistricts.isCity("4111100000")).isFalse();
    assertThat(CityDistricts.SQL_CITIES).startsWith("('41110','41130'").endsWith("'52110')");
  }
}
