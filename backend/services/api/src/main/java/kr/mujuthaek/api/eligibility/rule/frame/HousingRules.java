package kr.mujuthaek.api.eligibility.rule.frame;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Optional;
import java.util.OptionalLong;
import java.util.Set;
import kr.mujuthaek.api.eligibility.rule.BaseValueKind;
import kr.mujuthaek.api.eligibility.rule.BaseValues;
import kr.mujuthaek.api.eligibility.rule.DepositRegion;
import kr.mujuthaek.api.eligibility.rule.SubscriptionDeposits;
import kr.mujuthaek.api.eligibility.rule.Verdict;
import kr.mujuthaek.api.eligibility.rule.frame.Applicant.Household;
import kr.mujuthaek.api.eligibility.rule.frame.Criterion.Asset;
import kr.mujuthaek.api.eligibility.rule.frame.Criterion.Bonus;
import kr.mujuthaek.api.eligibility.rule.frame.Criterion.BonusCombine;
import kr.mujuthaek.api.eligibility.rule.frame.Criterion.Car;
import kr.mujuthaek.api.eligibility.rule.frame.Criterion.Factor;
import kr.mujuthaek.api.eligibility.rule.frame.Criterion.FactorKind;
import kr.mujuthaek.api.eligibility.rule.frame.Criterion.Homeless;
import kr.mujuthaek.api.eligibility.rule.frame.Criterion.Income;
import kr.mujuthaek.api.eligibility.rule.frame.Criterion.PrintedRow;
import kr.mujuthaek.api.eligibility.rule.frame.Criterion.RaisedLimit;
import kr.mujuthaek.api.eligibility.rule.frame.Criterion.Savings;

/**
 * 주거 조건: 무주택, 소득, 총자산, 자동차, 청약통장.
 *
 * <p>가산·한도 완화의 해당 여부를 모르면(맞벌이 미입력 등) 해당할 때와 아닐 때를 둘 다 계산해서, 결과가 같으면 그 결과로, 다르면 확인 필요로 둬요.
 */
final class HousingRules {

  private static final BigDecimal HUNDRED = BigDecimal.valueOf(100);

  private final BaseValues baseValues;
  private final SubscriptionDeposits deposits;

  HousingRules(BaseValues baseValues, SubscriptionDeposits deposits) {
    this.baseValues = baseValues;
    this.deposits = deposits;
  }

  static Evaluation homeless(Homeless c, Applicant a) {
    String summary =
        (c.scope() == Criterion.HomelessScope.HOUSEHOLD ? "세대 전원 무주택" : "본인 무주택")
            + (c.minYears() == null ? "" : ", 무주택 " + c.minYears() + "년 이상");
    Household h = a.household();
    Boolean homeless;
    Input input;
    if (c.scope() == Criterion.HomelessScope.HOUSEHOLD) {
      homeless = h.homeless();
      input = Input.HOMELESS;
    } else {
      // 본인 답이 없어도 세대 전원이 무주택이면 본인도 무주택이에요
      homeless =
          h.applicantHomeless() != null
              ? h.applicantHomeless()
              : (Boolean.TRUE.equals(h.homeless()) ? Boolean.TRUE : null);
      input = Input.APPLICANT_HOMELESS;
    }
    if (homeless == null) {
      return Evaluation.unknown(c, summary, "무주택 여부가 없어요", input);
    }
    if (!homeless) {
      return Evaluation.notMet(c, summary, null);
    }
    if (c.minYears() == null) {
      return Evaluation.met(c, summary);
    }
    if (h.homelessYears() == null) {
      return Evaluation.unknown(c, summary, "무주택 기간이 없어요", Input.HOMELESS_YEARS);
    }
    return Evaluation.decided(c, h.homelessYears() >= c.minYears(), summary);
  }

  Evaluation savings(Savings c, Applicant a, LocalDate on) {
    Applicant.Subscription s = a.subscription();
    if (c.minMonths() == null
        && c.minPayments() == null
        && c.minBalanceWon() == null
        && c.depositAreaM2() == null) {
      String summary = "청약통장 보유";
      if (s.months() == null) {
        return Evaluation.unknown(c, summary, "청약통장 가입 개월이 없어요", Input.SUBSCRIPTION_MONTHS);
      }
      return Evaluation.decided(c, s.months() >= 1, summary);
    }
    List<String> parts = new ArrayList<>();
    List<Verdict> verdicts = new ArrayList<>();
    Set<Input> missing = new LinkedHashSet<>();
    String reason = null;
    if (c.minMonths() != null) {
      parts.add("가입 " + c.minMonths() + "개월 이상");
      verdicts.add(atLeast(s.months(), c.minMonths(), Input.SUBSCRIPTION_MONTHS, missing));
    }
    if (c.minPayments() != null) {
      parts.add("납입 " + c.minPayments() + "회 이상");
      verdicts.add(atLeast(s.payments(), c.minPayments(), Input.SUBSCRIPTION_PAYMENTS, missing));
    }
    if (c.minBalanceWon() != null) {
      parts.add("예치금 " + Texts.won(c.minBalanceWon()) + " 이상");
      verdicts.add(atLeast(s.balanceWon(), c.minBalanceWon(), Input.SUBSCRIPTION_BALANCE, missing));
    }
    if (c.depositAreaM2() != null) {
      parts.add(
          "예치금이 예치기준금액(전용 "
              + c.depositAreaM2().stripTrailingZeros().toPlainString()
              + "㎡, 거주지별) 이상");
      DepositLimit limit = depositLimit(c.depositAreaM2(), a, on);
      if (limit.amountWon() != null) {
        verdicts.add(
            atLeast(s.balanceWon(), limit.amountWon(), Input.SUBSCRIPTION_BALANCE, missing));
      } else {
        verdicts.add(Verdict.UNKNOWN);
        missing.addAll(limit.inputs());
        // 주소지만 넣으면 기준금액이 정해지니, 예치금도 비어 있으면 같이 물어봐요
        if (!limit.inputs().isEmpty() && s.balanceWon() == null) {
          missing.add(Input.SUBSCRIPTION_BALANCE);
        }
        reason = limit.reason();
      }
    }
    String summary = "청약통장 " + String.join(", ", parts);
    Verdict all = Verdict.all(verdicts);
    if (all == Verdict.UNKNOWN) {
      return Evaluation.unknown(c, summary, reason == null ? "청약통장 정보가 부족해요" : reason, missing);
    }
    return Evaluation.decided(c, all == Verdict.MET, summary);
  }

  /** 예치기준금액(주택공급에 관한 규칙 별표 2): 공고일 현재 신청자 주민등록 거주지의 지역 열과 주택 전용면적의 칸. 정할 수 없으면 이유와 필요한 입력을 돌려줘요. */
  private DepositLimit depositLimit(BigDecimal areaM2, Applicant a, LocalDate on) {
    if (a.residenceRegionCode() == null) {
      return new DepositLimit(
          null, "주민등록 거주지가 있어야 예치기준금액을 고를 수 있어요", Set.of(Input.RESIDENCE_REGION));
    }
    Optional<DepositRegion> region = DepositRegion.of(a.residenceRegionCode(), on);
    if (region.isEmpty()) {
      return new DepositLimit(
          null,
          "거주지 시도가 예치기준금액 표(별표 2)의 어느 지역 열인지 정할 수 없어요 (예: 2026-07-01 출범한 전남광주통합특별시)",
          Set.of());
    }
    OptionalLong amount = deposits.find(on, region.get(), areaM2);
    if (amount.isEmpty()) {
      return new DepositLimit(null, "기준값 표에 그날의 예치기준금액이 없어요", Set.of());
    }
    return new DepositLimit(amount.getAsLong(), null, Set.of());
  }

  private record DepositLimit(Long amountWon, String reason, Set<Input> inputs) {}

  private static Verdict atLeast(Number value, long min, Input input, Set<Input> missing) {
    if (value == null) {
      missing.add(input);
      return Verdict.UNKNOWN;
    }
    return Verdict.of(value.longValue() >= min);
  }

  // ── 소득 ──────────────────────────────────────────────

  Evaluation income(Income c, Applicant a, LocalDate on) {
    Household h = a.household();
    return switch (c.basis()) {
      case HOUSEHOLD -> household(c, a, on, "");
      case APPLICANT -> applicant(c, a, on, "");
      case APPLICANT_AND_PARENTS -> {
        Set<Input> missing = new LinkedHashSet<>();
        if (h.applicantMonthlyIncomeWon() == null) {
          missing.add(Input.APPLICANT_INCOME);
        }
        if (h.parentsMonthlyIncomeWon() == null) {
          missing.add(Input.PARENTS_INCOME);
        }
        Long income =
            missing.isEmpty() ? h.applicantMonthlyIncomeWon() + h.parentsMonthlyIncomeWon() : null;
        yield incomeFor(
            c,
            a,
            on,
            "본인+부모 ",
            income,
            missing,
            h.applicantAndParentsSize(),
            Input.APPLICANT_AND_PARENTS_SIZE);
      }
      case HOUSEHOLD_IF_HEAD -> {
        if (Boolean.TRUE.equals(h.head())) {
          yield household(c, a, on, "(세대주) ");
        }
        if (Boolean.FALSE.equals(h.head())) {
          yield applicant(c, a, on, "(세대원) ");
        }
        Evaluation asHead = household(c, a, on, "");
        Evaluation asMember = applicant(c, a, on, "");
        String summary = "세대주면 " + asHead.summary() + ", 세대원이면 " + asMember.summary();
        if (asHead.verdict() == asMember.verdict() && asHead.verdict() != Verdict.UNKNOWN) {
          yield new Evaluation(c, asHead.verdict(), summary, null, List.of(), List.of());
        }
        Set<Input> missing = new LinkedHashSet<>(List.of(Input.HOUSEHOLD_HEAD));
        missing.addAll(asHead.missing());
        missing.addAll(asMember.missing());
        yield Evaluation.unknown(c, summary, "세대주인지에 따라 기준이 달라져요", missing);
      }
    };
  }

  private Evaluation household(Income c, Applicant a, LocalDate on, String prefix) {
    Household h = a.household();
    Set<Input> missing = new LinkedHashSet<>();
    if (h.monthlyIncomeWon() == null) {
      missing.add(Input.HOUSEHOLD_INCOME);
    }
    return incomeFor(
        c, a, on, prefix + "세대 ", h.monthlyIncomeWon(), missing, h.size(), Input.HOUSEHOLD_SIZE);
  }

  private Evaluation applicant(Income c, Applicant a, LocalDate on, String prefix) {
    Household h = a.household();
    Set<Input> missing = new LinkedHashSet<>();
    if (h.applicantMonthlyIncomeWon() == null) {
      missing.add(Input.APPLICANT_INCOME);
    }
    return incomeFor(c, a, on, prefix + "본인 ", h.applicantMonthlyIncomeWon(), missing, 1, null);
  }

  private Evaluation incomeFor(
      Income c,
      Applicant a,
      LocalDate on,
      String who,
      Long income,
      Set<Input> incomeMissing,
      Integer size,
      Input sizeInput) {
    if (size == null) {
      Set<Input> missing = new LinkedHashSet<>(List.of(sizeInput));
      missing.addAll(incomeMissing);
      return Evaluation.unknown(c, who + "월소득 " + standardText(c), "가구원 수가 없어요", missing);
    }
    Limit limit = limit(c, a, on, size, who);
    if (limit.problem() != null) {
      return Evaluation.unknown(c, limit.summary(), limit.problem());
    }
    if (income == null) {
      return Evaluation.unknown(c, limit.summary(), "월소득이 없어요", incomeMissing);
    }
    if (income <= limit.low()) {
      return Evaluation.met(c, limit.summary());
    }
    if (income > limit.high()) {
      return Evaluation.notMet(c, limit.summary(), null);
    }
    return Evaluation.unknown(c, limit.summary(), "가산에 해당하는지에 따라 결과가 달라져요", limit.missing());
  }

  /**
   * 기준 금액. 가산 해당 여부를 모르면 low(가산 없이)~high(가산 포함) 범위가 돼요.
   *
   * @param problem 계산할 수 없는 이유 (기준값 없음, 공고 금액표와 다름 …). 있으면 확인 필요
   */
  private record Limit(long low, long high, String summary, String problem, Set<Input> missing) {}

  private Limit limit(Income c, Applicant a, LocalDate on, int size, String who) {
    PrintedRow printed =
        c.printedTable().stream().filter(r -> r.householdSize() == size).findFirst().orElse(null);
    if (c.standard() == null) {
      if (printed == null) {
        String summary = who + "월소득: 공고 금액표 기준";
        return new Limit(0, 0, summary, "공고 금액표에 " + size + "인 금액이 없어요", Set.of());
      }
      String summary = who + "월소득 " + Texts.won(printed.maxWon()) + " 이하 (공고 금액표 " + size + "인)";
      return new Limit(printed.maxWon(), printed.maxWon(), summary, null, Set.of());
    }
    String table = standardLabel(c.standard()) + " " + c.year() + "년 " + size + "인";
    OptionalLong base =
        baseValues.find(BaseValueKind.valueOf(c.standard().name()), c.year(), "", size);
    if (base.isEmpty()) {
      return new Limit(
          0, 0, who + "월소득 " + standardText(c), "기준값 표에 " + table + " 값이 아직 없어요", Set.of());
    }
    Set<Input> missing = new LinkedHashSet<>();
    BigDecimal sureSum = BigDecimal.ZERO;
    BigDecimal maybeSum = BigDecimal.ZERO;
    BigDecimal sureMax = BigDecimal.ZERO;
    BigDecimal anyMax = BigDecimal.ZERO;
    BigDecimal sizeSum = BigDecimal.ZERO;
    BigDecimal sizeMax = BigDecimal.ZERO;
    for (Bonus bonus : c.bonuses()) {
      Boolean applies = applies(bonus.when(), a, on, size, missing);
      if (Boolean.TRUE.equals(applies)) {
        sureSum = sureSum.add(bonus.addPercent());
        sureMax = sureMax.max(bonus.addPercent());
        anyMax = anyMax.max(bonus.addPercent());
        if (bonus.when().factor() == FactorKind.HOUSEHOLD_SIZE) {
          sizeSum = sizeSum.add(bonus.addPercent());
          sizeMax = sizeMax.max(bonus.addPercent());
        }
      } else if (applies == null) {
        maybeSum = maybeSum.add(bonus.addPercent());
        anyMax = anyMax.max(bonus.addPercent());
      }
    }
    boolean sum = c.bonusCombine() == BonusCombine.SUM;
    BigDecimal lowPercent = c.percent().add(sum ? sureSum : sureMax);
    BigDecimal highPercent = c.percent().add(sum ? sureSum.add(maybeSum) : anyMax);
    long low = amount(base.getAsLong(), lowPercent);
    long high = amount(base.getAsLong(), highPercent);
    String summary =
        who
            + "월소득 "
            + Texts.won(low)
            + " 이하"
            + (high > low ? " (가산에 해당하면 " + Texts.won(high) + " 이하)" : "")
            + " ("
            + table
            + " × "
            + Texts.percent(lowPercent)
            + ")";
    if (printed != null) {
      long expected = amount(base.getAsLong(), c.percent().add(sum ? sizeSum : sizeMax));
      if (expected != printed.maxWon()) {
        String problem =
            "공고 금액표("
                + Texts.won(printed.maxWon())
                + ")와 기준값으로 계산한 금액("
                + Texts.won(expected)
                + ")이 달라요";
        return new Limit(low, high, summary, problem, Set.of());
      }
    }
    return new Limit(low, high, summary, null, missing);
  }

  /** 기준값 × 비율 ÷ 100, 원 단위 반올림. */
  private static long amount(long base, BigDecimal percent) {
    return BigDecimal.valueOf(base)
        .multiply(percent)
        .divide(HUNDRED, 0, RoundingMode.HALF_UP)
        .longValueExact();
  }

  private static String standardText(Income c) {
    if (c.standard() == null) {
      return "공고 금액표 기준";
    }
    return standardLabel(c.standard()) + " " + c.year() + "년 × " + Texts.percent(c.percent());
  }

  private static String standardLabel(Criterion.IncomeStandard standard) {
    return switch (standard) {
      case MEDIAN_INCOME -> "기준 중위소득";
      case URBAN_WORKER_INCOME -> "도시근로자 가구원수별 월평균소득";
      case URBAN_WORKER_AVERAGE_INCOME -> "도시근로자 가구당 월평균소득";
    };
  }

  // ── 총자산·자동차 ───────────────────────────────────────

  static Evaluation asset(Asset c, Applicant a, LocalDate on) {
    boolean household = c.basis() == Criterion.AssetBasis.HOUSEHOLD;
    Household h = a.household();
    return limited(
        c,
        a,
        on,
        household ? "세대 총자산" : "본인 총자산",
        household ? h.totalAssetWon() : h.applicantTotalAssetWon(),
        household ? Input.TOTAL_ASSET : Input.APPLICANT_TOTAL_ASSET,
        c.maxWon(),
        c.raisedLimits());
  }

  static Evaluation car(Car c, Applicant a, LocalDate on) {
    return limited(
        c,
        a,
        on,
        "자동차가액",
        a.household().carValueWon(),
        Input.CAR_VALUE,
        c.maxWon(),
        c.raisedLimits());
  }

  /** 한도 = maxWon과 해당하는 완화 한도 중 가장 큰 금액. */
  private static Evaluation limited(
      Criterion c,
      Applicant a,
      LocalDate on,
      String label,
      Long value,
      Input input,
      long maxWon,
      List<RaisedLimit> raised) {
    Set<Input> missing = new LinkedHashSet<>();
    long low = maxWon;
    long high = maxWon;
    for (RaisedLimit r : raised) {
      Boolean applies = applies(r.when(), a, on, a.household().size(), missing);
      if (Boolean.TRUE.equals(applies)) {
        low = Math.max(low, r.maxWon());
        high = Math.max(high, r.maxWon());
      } else if (applies == null) {
        high = Math.max(high, r.maxWon());
      }
    }
    String summary =
        label
            + " "
            + Texts.won(low)
            + " 이하"
            + (high > low ? " (한도 완화에 해당하면 " + Texts.won(high) + " 이하)" : "");
    if (value == null) {
      return Evaluation.unknown(c, summary, label + "이 없어요", input);
    }
    if (value <= low) {
      return Evaluation.met(c, summary);
    }
    if (value > high) {
      return Evaluation.notMet(c, summary, null);
    }
    return Evaluation.unknown(c, summary, "한도 완화에 해당하는지에 따라 결과가 달라져요", missing);
  }

  // ── 가산·한도 완화 요인 ──────────────────────────────────

  /**
   * 요인에 해당하는지. 모르면 null이고 missing에 필요한 입력을 더해요.
   *
   * @param size 소득은 기준에 쓰는 가구원 수, 자산은 세대 가구원 수 (모르면 null)
   */
  private static Boolean applies(
      Factor f, Applicant a, LocalDate on, Integer size, Set<Input> missing) {
    return switch (f.factor()) {
      case HOUSEHOLD_SIZE -> {
        if (size == null) {
          missing.add(Input.HOUSEHOLD_SIZE);
          yield null;
        }
        yield inRange(size, f);
      }
      case DUAL_INCOME -> {
        Boolean dual = a.household().dualIncome();
        if (dual == null) {
          missing.add(Input.DUAL_INCOME);
        }
        yield dual;
      }
      case CHILDREN -> childCount(f, a, on, missing, false);
      case NEWBORN_CHILDREN -> childCount(f, a, on, missing, true);
    };
  }

  private static Boolean childCount(
      Factor f, Applicant a, LocalDate on, Set<Input> missing, boolean newborn) {
    List<LocalDate> births = a.childBirthDates();
    if (births == null) {
      missing.add(Input.CHILD_BIRTH_DATES);
      return null;
    }
    if (a.expectingChild() != null) {
      return inRange(count(f, births, on, a.expectingChild(), newborn), f);
    }
    boolean without = inRange(count(f, births, on, false, newborn), f);
    boolean with = inRange(count(f, births, on, true, newborn), f);
    if (without == with) {
      return without;
    }
    missing.add(Input.EXPECTING_CHILD);
    return null;
  }

  private static int count(
      Factor f, List<LocalDate> births, LocalDate on, boolean unborn, boolean newborn) {
    return newborn
        ? Kids.newborns(births, on, f.since(), f.countRule(), unborn)
        : Kids.minors(births, on, unborn);
  }

  private static boolean inRange(int value, Factor f) {
    return (f.min() == null || value >= f.min()) && (f.max() == null || value <= f.max());
  }
}
