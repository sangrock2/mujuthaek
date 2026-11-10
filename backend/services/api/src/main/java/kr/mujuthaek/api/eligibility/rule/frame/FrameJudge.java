package kr.mujuthaek.api.eligibility.rule.frame;

import java.time.LocalDate;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import kr.mujuthaek.api.eligibility.rule.BaseValues;
import kr.mujuthaek.api.eligibility.rule.Eligibility;
import kr.mujuthaek.api.eligibility.rule.SubscriptionDeposits;
import kr.mujuthaek.api.eligibility.rule.Verdict;
import kr.mujuthaek.api.eligibility.rule.frame.FrameJudgment.GroupResult;
import kr.mujuthaek.api.eligibility.rule.frame.FrameJudgment.PreferenceResult;
import kr.mujuthaek.api.eligibility.rule.frame.FrameJudgment.Purpose;
import kr.mujuthaek.api.eligibility.rule.frame.FrameJudgment.Question;

/**
 * 판정 틀 하나를 판정해요 (세 분야 공통).
 *
 * <ol>
 *   <li>조건마다 충족·불충족·확인 필요를 정해요. 조건의 asOf가 있으면 그날, 없으면 틀의 referenceDate 기준이에요.
 *   <li>대상군 하나 = 공통 조건 + 그 대상군 조건을 모두 충족해야 충족.
 *   <li>공고 = 대상군 중 하나라도 충족이면 지원 가능, 충족은 없고 확인 필요가 있으면 확인 필요, 모두 불충족이면 지원 불가.
 *   <li>내 순위 = 충족한 대상군 중 가장 앞 신청 순위(rank). 순위가 없는 공고는 null.
 *   <li>우대는 따로 계산해서 표시만 해요 (지원 가능 여부는 바꾸지 않아요).
 * </ol>
 *
 * <p>모르는 값이 섞여도 결과가 정해지면 정해요. 예: 불충족 조건이 하나 있으면 나머지를 몰라도 그 대상군은 불충족이에요.
 */
public final class FrameJudge {

  private final HousingRules housing;

  /**
   * @param baseValues 소득 기준표 (기준 중위소득, 도시근로자 월평균소득)
   * @param deposits 청약 예치기준금액 표 (주택공급에 관한 규칙 별표 2)
   */
  public FrameJudge(BaseValues baseValues, SubscriptionDeposits deposits) {
    this.housing = new HousingRules(baseValues, deposits);
  }

  /** 기준일이 있는 틀을 판정해요 (주거·사업공간 틀은 항상 있어요). */
  public FrameJudgment judge(Frame frame, Applicant applicant) {
    if (frame.referenceDate() == null) {
      throw new IllegalArgumentException("기준일이 없는 틀은 판정하는 날을 같이 넘겨야 해요");
    }
    return judge(frame, applicant, frame.referenceDate());
  }

  /**
   * @param judgedOn 판정하는 날. 틀에 기준일(referenceDate)이 없으면(기준일 문구가 없는 창업지원 공고) 이날 기준으로 계산해요
   */
  public FrameJudgment judge(Frame frame, Applicant applicant, LocalDate judgedOn) {
    LocalDate day = frame.referenceDate() != null ? frame.referenceDate() : judgedOn;
    List<Evaluation> common = evaluateAll(frame.common(), applicant, day);
    List<Verdict> commonVerdicts = common.stream().map(Evaluation::verdict).toList();

    List<GroupResult> groups = new ArrayList<>();
    for (Frame.Group group : frame.groups()) {
      List<Evaluation> criteria = evaluateAll(group.criteria(), applicant, day);
      List<Verdict> verdicts = new ArrayList<>(commonVerdicts);
      criteria.forEach(e -> verdicts.add(e.verdict()));
      groups.add(new GroupResult(group, Verdict.all(verdicts), criteria));
    }
    Eligibility result =
        Eligibility.of(Verdict.any(groups.stream().map(GroupResult::verdict).toList()));

    List<PreferenceResult> preferences = new ArrayList<>();
    for (Frame.Preference preference : frame.preferences()) {
      List<Evaluation> criteria = evaluateAll(preference.criteria(), applicant, day);
      preferences.add(
          new PreferenceResult(
              preference,
              Verdict.all(criteria.stream().map(Evaluation::verdict).toList()),
              criteria));
    }

    return new FrameJudgment(
        frame.field(),
        result,
        bestRank(groups),
        day,
        common,
        groups,
        preferences,
        frame.notes(),
        questions(frame, applicant),
        result == Eligibility.NEEDS_INPUT ? missingInputs(common, groups) : List.of());
  }

  /** 내 순위: 충족한 대상군 중 가장 앞 순위. 1순위는 불충족, 2순위는 충족이면 2예요. */
  private static Integer bestRank(List<GroupResult> groups) {
    return groups.stream()
        .filter(g -> g.verdict() == Verdict.MET && g.group().rank() != null)
        .map(g -> g.group().rank())
        .min(Integer::compare)
        .orElse(null);
  }

  private List<Evaluation> evaluateAll(
      List<Criterion> criteria, Applicant applicant, LocalDate frameDay) {
    return criteria.stream().map(c -> evaluate(c, applicant, frameDay)).toList();
  }

  Evaluation evaluate(Criterion criterion, Applicant a, LocalDate frameDay) {
    LocalDate on = criterion.meta().asOf() != null ? criterion.meta().asOf() : frameDay;
    Evaluation evaluation =
        switch (criterion) {
          case Criterion.Age c -> PersonRules.age(c, a, on);
          case Criterion.Nationality c -> PersonRules.nationality(c, a);
          case Criterion.Residence c -> PersonRules.residence(c, a);
          case Criterion.Region c -> PersonRules.region(c, a);
          case Criterion.Marriage c -> PersonRules.marriage(c, a, on);
          case Criterion.Children c -> PersonRules.children(c, a, on);
          case Criterion.Status c -> PersonRules.status(c, a);
          case Criterion.ExcludedStatus c -> PersonRules.excludedStatus(c, a);
          case Criterion.Homeless c -> HousingRules.homeless(c, a);
          case Criterion.Income c -> housing.income(c, a, on);
          case Criterion.Asset c -> HousingRules.asset(c, a, on);
          case Criterion.Car c -> HousingRules.car(c, a, on);
          case Criterion.Savings c -> housing.savings(c, a, on);
          case Criterion.ApplicantKind c -> BusinessRules.applicantKind(c, a);
          case Criterion.BusinessRegistration c -> BusinessRules.registration(c, a, on);
          case Criterion.BusinessCareer c -> BusinessRules.career(c, a, on);
          case Criterion.BusinessAge c -> BusinessRules.age(c, a, on);
          case Criterion.BusinessAgeYears c -> BusinessRules.ageInYears(c, a, on);
          case Criterion.Closure c -> BusinessRules.closure(c, a, on);
          case Criterion.Revenue c -> BusinessRules.revenue(c, a);
          case Criterion.Industry c -> BusinessRules.industry(c, a);
          case Criterion.AnyOf c -> anyOf(c, a, frameDay);
          case Criterion.Ask c -> PersonRules.ask(c, a);
        };
    return criterion.meta().inReview() ? evaluation.inReview() : evaluation;
  }

  /** 여러 길 중 하나: 길 하나 = 그 안 조건을 모두 충족. 길 중 하나라도 충족이면 충족이에요. */
  private Evaluation anyOf(Criterion.AnyOf c, Applicant a, LocalDate frameDay) {
    List<Evaluation.OptionResult> options = new ArrayList<>();
    Set<Input> missing = new LinkedHashSet<>();
    for (Criterion.Option option : c.options()) {
      List<Evaluation> criteria = evaluateAll(option.criteria(), a, frameDay);
      Verdict verdict = Verdict.all(criteria.stream().map(Evaluation::verdict).toList());
      if (verdict == Verdict.UNKNOWN) {
        criteria.stream()
            .filter(e -> e.verdict() == Verdict.UNKNOWN)
            .forEach(e -> missing.addAll(e.missing()));
      }
      options.add(new Evaluation.OptionResult(option.label(), verdict, criteria));
    }
    Verdict verdict = Verdict.any(options.stream().map(Evaluation.OptionResult::verdict).toList());
    String summary =
        "다음 중 하나: "
            + String.join(" / ", options.stream().map(Evaluation.OptionResult::label).toList());
    String reason = verdict == Verdict.UNKNOWN ? "아직 정해지지 않은 길이 있어요" : null;
    List<Input> needs = verdict == Verdict.UNKNOWN ? List.copyOf(missing) : List.of();
    return new Evaluation(c, verdict, summary, reason, needs, options);
  }

  /** 틀 안의 모든 질문 (공통 → 대상군 → 우대 순서, ANY_OF 안쪽 포함). */
  private static List<Question> questions(Frame frame, Applicant a) {
    Map<String, Question> found = new LinkedHashMap<>();
    collectQuestions(frame.common(), a, Purpose.ELIGIBILITY, found);
    frame.groups().forEach(g -> collectQuestions(g.criteria(), a, Purpose.ELIGIBILITY, found));
    frame.preferences().forEach(p -> collectQuestions(p.criteria(), a, Purpose.PREFERENCE, found));
    return List.copyOf(found.values());
  }

  private static void collectQuestions(
      List<Criterion> criteria, Applicant a, Purpose purpose, Map<String, Question> found) {
    for (Criterion c : criteria) {
      if (c instanceof Criterion.Ask ask) {
        found.putIfAbsent(
            ask.id(), new Question(ask.id(), ask.question(), a.answers().get(ask.id()), purpose));
      } else if (c instanceof Criterion.AnyOf any) {
        any.options().forEach(o -> collectQuestions(o.criteria(), a, purpose, found));
      }
    }
  }

  /** 결과가 확인 필요일 때만: 아직 정해지지 않은 대상군과 공통 조건이 필요로 하는 입력. */
  private static List<Input> missingInputs(List<Evaluation> common, List<GroupResult> groups) {
    Set<Input> missing = new LinkedHashSet<>();
    common.stream()
        .filter(e -> e.verdict() == Verdict.UNKNOWN)
        .forEach(e -> missing.addAll(e.missing()));
    groups.stream()
        .filter(g -> g.verdict() == Verdict.UNKNOWN)
        .flatMap(g -> g.criteria().stream())
        .filter(e -> e.verdict() == Verdict.UNKNOWN)
        .forEach(e -> missing.addAll(e.missing()));
    return List.copyOf(missing);
  }
}
