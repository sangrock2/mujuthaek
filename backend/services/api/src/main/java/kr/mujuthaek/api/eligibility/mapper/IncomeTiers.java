package kr.mujuthaek.api.eligibility.mapper;

import java.util.ArrayList;
import java.util.List;
import java.util.Set;
import java.util.TreeSet;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import kr.mujuthaek.api.eligibility.rule.Judgment;
import kr.mujuthaek.api.eligibility.rule.Judgment.AnyOf;
import kr.mujuthaek.api.eligibility.rule.Judgment.Ask;
import kr.mujuthaek.api.eligibility.rule.Judgment.Asset;
import kr.mujuthaek.api.eligibility.rule.Judgment.Basics;
import kr.mujuthaek.api.eligibility.rule.Judgment.Car;
import kr.mujuthaek.api.eligibility.rule.Judgment.Criterion;
import kr.mujuthaek.api.eligibility.rule.Judgment.Group;
import kr.mujuthaek.api.eligibility.rule.Judgment.Income;

/**
 * 소득 구간으로 나뉜 대상군(「월평균소득 50% 이하 및 자산·자동차 기준 충족」)을 대상 대상군마다 「구간 중 하나」 조건으로 접어요.
 *
 * <p>추출은 순위·계층마다 소득 기준이 다르면 그 구간 이름을 대상군으로 적어요. 그대로 판정하면 구간 대상군에는 소득·자산 조건만 있어서 나이·거주지가 맞지 않아도 소득만
 * 맞으면 공고 전체가 지원 가능이 돼요(실측 2026-10-29 구로구 도전숙: 부산 거주 66세 세대원). 구간은 대상이 아니라 대상이 갖출 소득 기준 중 하나라서, 순위가
 * 없는 대상 대상군마다 구간 중 하나(구간이 하나면 그 조건 그대로)를 더하고 구간 대상군은 빼요.
 *
 * <p>「1순위 …」「2순위」처럼 순위로 나뉜 대상군만 있으면(대상 대상군이 없으면) 그대로 둬요. 새 추출은 추출 쪽에서 이미 접어서 오고(extraction
 * judgment/frame.py _fold_income_tiers), 이 클래스는 그 전에 저장된 공고도 같은 규칙으로 읽게 해요. 두 규칙은 같아야 해요.
 */
final class IncomeTiers {

  /** 소득 구간 이름: 「월평균소득 50% 이하」「월평균소득 50% 초과 ~100% 이하」「소득 70% 이하」 */
  static final Pattern TIER_NAME = Pattern.compile("소득\\D{0,6}\\d+(?:\\.\\d+)?\\s*%");

  /** 신청 순위: 「1순위」「제2순위」. 「1·2순위」처럼 숫자가 여럿이면 한 순위로 정하지 않아요 (extraction rank_of와 같음) */
  private static final Pattern RANK =
      Pattern.compile("제?\\s*(\\d+)((?:\\s*(?:[·ㆍ,~∼\\-]|및|또는)\\s*\\d+)*)\\s*순위");

  private IncomeTiers() {}

  static List<Group> fold(List<Group> groups) {
    List<Group> tiers = new ArrayList<>();
    List<Group> others = new ArrayList<>();
    for (Group g : groups) {
      boolean tier =
          g.name() != null
              && rank(g.name()) == null
              && TIER_NAME.matcher(g.name()).find()
              && financialOnly(g.criteria());
      (tier ? tiers : others).add(g);
    }
    boolean hasBase =
        others.stream()
            .anyMatch(g -> !"all".equals(g.id()) && (g.name() == null || rank(g.name()) == null));
    if (tiers.isEmpty() || !hasBase) {
      return groups;
    }
    List<Group> out = new ArrayList<>();
    for (Group g : others) {
      if ("all".equals(g.id()) || (g.name() != null && rank(g.name()) != null)) {
        out.add(g);
        continue;
      }
      List<Criterion> criteria = new ArrayList<>(g.criteria());
      if (tiers.size() == 1) {
        criteria.addAll(tiers.getFirst().criteria());
      } else {
        criteria.add(
            new AnyOf(
                new Basics(g.id() + "-income-tier", null, null, false, null),
                tiers.stream().map(t -> new Judgment.Option(t.name(), t.criteria())).toList()));
      }
      out.add(new Group(g.id(), g.name(), List.copyOf(criteria)));
    }
    return List.copyOf(out);
  }

  /** 이름의 신청 순위. 없거나 여럿이면 null. */
  static Integer rank(String name) {
    Set<Integer> found = new TreeSet<>();
    Matcher m = RANK.matcher(name);
    while (m.find()) {
      if (!m.group(2).isBlank()) {
        return null;
      }
      found.add(Integer.parseInt(m.group(1)));
    }
    return found.size() == 1 ? found.iterator().next() : null;
  }

  /** 소득·자산·자동차 조건뿐인지 (가구원 수 예외로 생긴 ANY_OF 안의 질문은 괜찮아요). 소득 조건이 하나는 있어야 해요. */
  static boolean financialOnly(List<Criterion> criteria) {
    boolean[] income = {false};
    return !criteria.isEmpty()
        && criteria.stream().allMatch(c -> financial(c, false, income))
        && income[0];
  }

  private static boolean financial(Criterion c, boolean nested, boolean[] income) {
    return switch (c) {
      case Income x -> income[0] = true;
      case Asset x -> true;
      case Car x -> true;
      case Ask x -> nested;
      case AnyOf x ->
          x.options().stream()
              .allMatch(o -> o.criteria().stream().allMatch(i -> financial(i, true, income)));
      default -> false;
    };
  }
}
