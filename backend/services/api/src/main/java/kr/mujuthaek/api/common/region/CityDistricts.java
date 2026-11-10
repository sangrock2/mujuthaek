package kr.mujuthaek.api.common.region;

import java.util.Set;
import java.util.stream.Collectors;

/**
 * 일반구가 있는 시와 그 구(법정동코드). 시군구 자리를 견주는 모든 곳(판정·규제지역·공고 검색·관심 지역 알림·혜택·사업공간)이 같은 목록을 써요.
 *
 * <p>구는 시의 코드 범위 안에서 붙어 앞부분이 시와 달라요(수원시 41110 → 장안구 41111·영통구 41117). 시군구 끝자리가 0이라는 모양만으로 시를 정하면
 * 영동군 43740 다음의 증평군 43745가 영동군의 구처럼 걸려, 곳마다 따로 짠 「앞 4자리」 규칙이 증평 주민에게 영동군 공고·조건을 맞다고 했어요(2026-11-10
 * 재검토). 그래서 시는 법정동코드표(2026-09-29, 폐지 안 된 것)에서 정한 목록으로 둬요. 구는 시 앞 4자리 + 끝자리가 0이 아닌 코드라 폐지된 구 코드(부천
 * 41191 등)도 그 시의 구로 봐요. 순수 자바라 eligibility/rule에서도 써요.
 */
public final class CityDistricts {

  /** 일반구가 있는 시(시군구 5자리). */
  public static final Set<String> CITIES =
      Set.of(
          "41110", "41130", "41170", "41190", "41270", "41280", "41460", "41590", "43110", "44130",
          "47110", "48120", "52110");

  /** SQL에 바로 넣는 시 목록(예: {@code ('41110','41130')}). 위 상수로만 만들어 그대로 넣어도 돼요. */
  public static final String SQL_CITIES =
      CITIES.stream().sorted().map(c -> "'" + c + "'").collect(Collectors.joining(",", "(", ")"));

  private CityDistricts() {}

  /** place(5자리 이상)가 일반구 있는 시 city(앞 5자리)의 구·동인지. 시 자신은 아니에요. */
  public static boolean inCity(String city, String place) {
    return city != null
        && place != null
        && city.length() >= 5
        && place.length() >= 5
        && CITIES.contains(city.substring(0, 5))
        && place.charAt(4) != '0'
        && place.startsWith(city.substring(0, 4));
  }

  /** place가 일반구(또는 그 안의 동)면 그 시 코드(5자리), 아니면 null. */
  public static String cityOf(String place) {
    if (place == null || place.length() < 5 || place.charAt(4) == '0') {
      return null;
    }
    String city = place.substring(0, 4) + "0";
    return CITIES.contains(city) ? city : null;
  }

  /** code가 일반구 있는 시 자체(시군구 자리 아래가 모두 0)인지. */
  public static boolean isCity(String code) {
    return code != null
        && code.length() >= 5
        && CITIES.contains(code.substring(0, 5))
        && code.substring(5).chars().allMatch(c -> c == '0');
  }

  /**
   * SQL 조건: 식 place가 식 city(시 코드)의 구·동인지. 두 식은 우리 코드가 정한 칸 이름·식이어야 해요(사용자 값을 넣지 않아요).
   *
   * @return 예: {@code (left(u, 5) in ('41110',…) and left(n, 4) = left(u, 4) and substr(n, 5, 1) <>
   *     '0')}
   */
  public static String sqlInCity(String city, String place) {
    return "(left(%s, 5) in %s and left(%s, 4) = left(%s, 4) and substr(%s, 5, 1) <> '0')"
        .formatted(city, SQL_CITIES, place, city, place);
  }
}
