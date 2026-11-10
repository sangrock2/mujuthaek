package kr.mujuthaek.api.eligibility.rule;

import java.time.LocalDate;
import java.util.ArrayList;
import java.util.EnumSet;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Optional;
import java.util.Set;
import java.util.stream.Collectors;

/**
 * 판정 틀 전체를 판정해요: 공급 대상(그룹)마다 공통 조건 + 그 대상의 조건을 모두 보고, 대상 중 하나라도 지원 가능하면 공고는 지원 가능이에요.
 *
 * <p>대상 하나만 통과해도 지원 가능이라, 추출이 기본 자격을 빠뜨린 대상이 있으면 그 대상으로 누구나 지원 가능이 돼요(2026-10-31 운영 「강북구 신혼부부
 * 매입임대」: 「총자산·자동차 기준은 소득 50% 이하인 자에 한함」이 자산·자동차만 가진 대상이 되어, 인천에 사는 61세 집 있는 미혼도 지원 가능). 그래서 질문 없이
 * 자동으로 판정되는 대상에 같은 공고의 다른 대상이 가진 무주택·소득 조건이 없으면, 그 대상은 확인 필요 항목({@link #PARTIAL_GROUP})을 하나 더 받아 지원
 * 가능까지 가지 않아요. 질문이 있는 대상은 질문이 늘 확인 필요라 그대로 둬요. 추출이 주택형·단지별 조건으로 대상을 나눈 공고(「그 밖의 주택형·단지」 대상이 있음)는
 * 대상마다 소득 기준이 다른 게 원문 그대로라 견주지 않아요.
 *
 * <p>결과에는 사용자가 보낸 값을 넣지 않아요.
 */
public final class Judge {

  /** 같은 공고의 다른 대상에 있는 기본 자격이 빠진 대상에 붙이는 확인 필요 항목. */
  public static final String PARTIAL_GROUP = "PARTIAL_GROUP";

  /**
   * 추출이 주택형·단지별 조건으로 대상을 나누고 남은 주택형에 붙이는 이름 (extraction judgment/frame.py의 REST). 이 대상이 있으면 대상마다 소득
   * 기준이 다른 게 원문 그대로예요.
   */
  static final String SCOPE_REST = "그 밖의 주택형·단지";

  /** 대상끼리 견주는 기본 자격. 거주지는 지역 우선 대상과 전국 대상처럼 대상마다 정상적으로 다를 수 있어 견주지 않아요. */
  private enum Base {
    HOMELESS("무주택"),
    INCOME("소득");

    private final String label;

    Base(String label) {
      this.label = label;
    }
  }

  private Judge() {}

  /**
   * @param missingInputs 지원 불가가 아닌 대상에서, 넣으면 판정이 바뀌는 입력 칸 (화면의 "입력" 버튼)
   */
  public record Result(Overall overall, List<Target> targets, List<String> missingInputs) {}

  /**
   * @param summary 조건 수 (화면의 "4개 조건 중 3개 충족 · 1개 확인 필요")
   */
  public record Target(
      String id, String name, Overall overall, Summary summary, List<Item> items) {}

  public record Summary(int total, int met, int notMet, int unknown) {}

  public static Result evaluate(Judgment judgment, Applicant applicant) {
    return evaluate(judgment, applicant, IncomeBenchmarks.NONE);
  }

  /**
   * @param benchmarks 공고에 인쇄된 소득표가 없을 때 쓰는 기준 소득 월액
   */
  public static Result evaluate(
      Judgment judgment, Applicant applicant, IncomeBenchmarks benchmarks) {
    LocalDate ref = judgment.referenceDate();
    List<Item> common =
        judgment.common().stream()
            .map(c -> CriterionJudge.judge(c, applicant, ref, benchmarks))
            .toList();
    List<Target> targets = new ArrayList<>();
    Set<String> missing = new LinkedHashSet<>();
    EnumSet<Base> noticeBases = EnumSet.noneOf(Base.class);
    boolean splitByScope =
        judgment.groups().stream().anyMatch(g -> g.name() != null && g.name().contains(SCOPE_REST));
    if (!splitByScope) {
      judgment.groups().forEach(g -> noticeBases.addAll(bases(g.criteria())));
    }
    for (Judgment.Group g : judgment.groups()) {
      List<Item> items = new ArrayList<>(common);
      g.criteria().forEach(c -> items.add(CriterionJudge.judge(c, applicant, ref, benchmarks)));
      partialGroup(judgment.common(), g, noticeBases).ifPresent(items::add);
      Overall overall = Overall.of(Status.all(items.stream().map(Item::status).toList()));
      targets.add(new Target(g.id(), g.name(), overall, summary(items), List.copyOf(items)));
      if (overall != Overall.INELIGIBLE) {
        items.forEach(i -> missing.addAll(i.needs()));
      }
    }
    Overall overall =
        targets.isEmpty()
            ? Overall.of(Status.all(common.stream().map(Item::status).toList()))
            : Overall.best(targets.stream().map(Target::overall).toList());
    return new Result(overall, List.copyOf(targets), List.copyOf(missing));
  }

  /**
   * 질문 없이 자동으로 판정되는 대상에, 같은 공고의 다른 대상이 가진 기본 자격(무주택·소득)이 공통 조건에도 그 대상에도 없으면 확인 필요 항목을 줘요. 질문(ASK)이
   * 있는 대상은 질문이 늘 확인 필요라 지원 가능이 될 수 없어서 건드리지 않아요. 택일(ANY_OF) 안의 질문은 다른 선택지로 충족될 수 있어 질문으로 치지 않고, 택일
   * 안의 무주택·소득은 그 대상이 가진 기본 자격으로 쳐요.
   */
  private static Optional<Item> partialGroup(
      List<Judgment.Criterion> common, Judgment.Group group, EnumSet<Base> noticeBases) {
    if (asks(common) || asks(group.criteria())) {
      return Optional.empty();
    }
    Set<Base> lacking = EnumSet.copyOf(noticeBases);
    lacking.removeAll(bases(common));
    lacking.removeAll(bases(group.criteria()));
    if (lacking.isEmpty()) {
      return Optional.empty();
    }
    String names = lacking.stream().map(b -> b.label).collect(Collectors.joining("·"));
    return Optional.of(
        new Item(
            group.id() + "-partial",
            PARTIAL_GROUP,
            "다른 대상에 있는 " + names + " 조건이 이 대상에는 없어요",
            Status.UNKNOWN,
            "원문에서 이 대상의 자격 조건을 확인해 주세요",
            List.of(),
            null,
            null,
            null));
  }

  private static boolean asks(List<Judgment.Criterion> criteria) {
    return criteria.stream().anyMatch(Judgment.Ask.class::isInstance);
  }

  private static Set<Base> bases(List<Judgment.Criterion> criteria) {
    Set<Base> found = EnumSet.noneOf(Base.class);
    for (Judgment.Criterion c : criteria) {
      switch (c) {
        case Judgment.Homeless h -> found.add(Base.HOMELESS);
        case Judgment.Income i -> found.add(Base.INCOME);
        case Judgment.AnyOf any -> any.options().forEach(o -> found.addAll(bases(o.criteria())));
        default -> {}
      }
    }
    return found;
  }

  static Summary summary(List<Item> items) {
    int met = 0;
    int notMet = 0;
    int unknown = 0;
    for (Item i : items) {
      switch (i.status()) {
        case MET -> met++;
        case NOT_MET -> notMet++;
        case UNKNOWN -> unknown++;
      }
    }
    return new Summary(items.size(), met, notMet, unknown);
  }
}
