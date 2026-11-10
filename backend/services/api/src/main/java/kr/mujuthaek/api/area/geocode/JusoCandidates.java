package kr.mujuthaek.api.area.geocode;

import java.util.List;
import java.util.Optional;
import java.util.function.Predicate;

/**
 * 검색 결과 중 공고 주소에 맞는 하나 고르기. 하나로 정해지지 않으면 고르지 않아요(엉뚱한 단지에 좌표를 주는 것보다 못 찾는 게 나아요).
 *
 * <p>검색 API는 비슷한 주소도 줘요(예: 구를 잘못 적은 "동구 초량상로 1-2"에는 동구의 초량상로35번길·105번길 1-2만 나옴 — 진짜는 중구). 그래서 아는 만큼
 * 좁혀요: 도로명이 같은 것 → 건물번호가 같은 것 → 법정동코드가 같은 것 → 시군구가 같은 것. 좁힌 결과가 없으면 그 조건은 건너뛰어요. 마지막에 하나(또는 모두 같은
 * 건물 출입구)만 남으면 골라요.
 */
public final class JusoCandidates {

  /**
   * 공고 주소에서 아는 것. 모르는 칸은 null.
   *
   * @param bjdCode 공고에서 받은 법정동코드 10자리
   * @param sigunguCode 주소에서 판별한 시군구 코드 5자리
   * @param roadName 주소 정리에서 뽑은 도로명 (공백은 무시하고 비교)
   */
  public record Hint(
      String bjdCode,
      String sigunguCode,
      String roadName,
      Integer buildingMain,
      Integer buildingSub) {

    public static Hint none() {
      return new Hint(null, null, null, null, null);
    }
  }

  private JusoCandidates() {}

  public static Optional<JusoResult> pick(List<JusoResult> results, Hint hint) {
    List<JusoResult> left = results;
    if (hint.roadName() != null) {
      String road = noSpaces(hint.roadName());
      left = narrow(left, r -> r.rn() != null && noSpaces(r.rn()).equals(road));
    }
    if (hint.buildingMain() != null) {
      int sub = hint.buildingSub() == null ? 0 : hint.buildingSub();
      left = narrow(left, r -> r.buildingMain() == hint.buildingMain() && r.buildingSub() == sub);
    }
    if (hint.bjdCode() != null) {
      left = narrow(left, r -> hint.bjdCode().equals(r.admCd()));
    }
    if (hint.sigunguCode() != null) {
      left = narrow(left, r -> hint.sigunguCode().equals(r.sigunguCode()));
    }
    if (left.size() == 1 || (!left.isEmpty() && sameEntrance(left))) {
      return Optional.of(left.getFirst());
    }
    return Optional.empty();
  }

  private static List<JusoResult> narrow(List<JusoResult> results, Predicate<JusoResult> match) {
    List<JusoResult> matched = results.stream().filter(match).toList();
    return matched.isEmpty() ? results : matched;
  }

  private static boolean sameEntrance(List<JusoResult> results) {
    String first = results.getFirst().roadKey();
    return results.stream().allMatch(r -> r.roadKey().equals(first));
  }

  private static String noSpaces(String s) {
    return s.replace(" ", "");
  }
}
