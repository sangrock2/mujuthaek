package kr.mujuthaek.api.eligibility.rule.frame;

import java.util.ArrayList;
import java.util.List;
import kr.mujuthaek.api.common.region.CityDistricts;
import kr.mujuthaek.api.eligibility.rule.Verdict;

/**
 * 법정동코드 비교. 코드는 시도 2 + 시군구 3 + 읍면동 3 + 리 2자리이고, 모르는 하위 단계는 0이에요.
 *
 * <p>조건이 "서울(1100000000)"이면 서울의 모든 시군구가 해당돼요. 사용자가 시도만 넣었는데 조건이 시군구면 알 수 없어서 확인 필요예요.
 */
public final class RegionCodes {

  private static final int[] LEVEL_ENDS = {2, 5, 8, 10};

  private RegionCodes() {}

  /** 2·5·8·10자리 숫자인지. */
  public static boolean valid(String code) {
    return code != null && code.matches("\\d{2}|\\d{5}|\\d{8}|\\d{10}");
  }

  /** 사용자 지역이 조건 지역 목록 중 하나 안에 있는지. */
  public static Verdict withinAny(String userCode, List<String> conditionCodes) {
    List<Verdict> verdicts = new ArrayList<>();
    for (String code : conditionCodes) {
      verdicts.add(within(userCode, code));
    }
    return Verdict.any(verdicts);
  }

  /** 사용자 지역이 조건 지역 안에 있는지. */
  static Verdict within(String userCode, String conditionCode) {
    String user = significant(userCode);
    String condition = significant(conditionCode);
    if (user.isEmpty() || condition.isEmpty()) {
      return Verdict.UNKNOWN;
    }
    if (user.startsWith(condition) || cityHasDistrict(condition, user)) {
      return Verdict.MET;
    }
    // 사용자 코드가 더 짧고 조건이 그 안의 지역이면 (예: 사용자 "경기", 조건 "수원") 더 자세한 주소가 있어야 알 수 있어요.
    // 일반구가 있는 시만 넣었는데 조건이 그 시의 구여도 같아요 (사용자 "수원시", 조건 "장안구")
    return condition.startsWith(user) || cityHasDistrict(user, condition)
        ? Verdict.UNKNOWN
        : Verdict.NOT_MET;
  }

  /**
   * 일반구가 있는 시(공통 목록 CityDistricts, 예: 수원시 41110)와 그 시의 구·동(예: 장안구 41111). 구는 시의 코드 범위 안에서 붙어 앞부분이
   * 시와 달라요: 앞부분 일치만 보면 「수원시 거주」 조건에 장안구 주민이 불충족이 됐어요(2026-11-10 코드 검토). 시는 모양(끝자리 0)이 아니라 목록으로
   * 정해요(재검토: 영동군 43740 조건에 증평군 43745 주민이 충족이 됐음).
   */
  static boolean cityHasDistrict(String city, String place) {
    return city.length() == 5 && CityDistricts.inCity(city, place);
  }

  /** 0으로 채운 하위 단계를 뺀 앞부분. 예: 1100000000 → 11, 4311100000 → 43111, 52730 → 52730. */
  static String significant(String code) {
    if (!valid(code)) {
      return "";
    }
    int end = 2;
    int start = 0;
    for (int levelEnd : LEVEL_ENDS) {
      if (levelEnd > code.length()) {
        break;
      }
      if (!code.substring(start, levelEnd).chars().allMatch(c -> c == '0')) {
        end = levelEnd;
      }
      start = levelEnd;
    }
    return code.substring(0, end);
  }
}
