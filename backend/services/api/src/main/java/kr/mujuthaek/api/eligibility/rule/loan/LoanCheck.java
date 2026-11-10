package kr.mujuthaek.api.eligibility.rule.loan;

import java.time.LocalDate;
import java.time.Period;
import java.util.ArrayList;
import java.util.EnumSet;
import java.util.List;
import java.util.Set;
import kr.mujuthaek.api.eligibility.rule.Eligibility;
import kr.mujuthaek.api.eligibility.rule.Verdict;
import kr.mujuthaek.api.eligibility.rule.frame.Applicant.MaritalStatus;

/**
 * 대출 상품 하나의 자격을 사용자 입력에 맞춰 봐요. 공고와 상관없이 사람 조건만 봐요. 조건마다 충족·불충족·확인 필요를 내고, 모두 충족해야 받을 수 있어요.
 *
 * <p>상품안내 공통 조건 중 "세대원 전원 무주택"은 모든 상품에 봐요. "세대주(예비 세대주 포함)"는 대출을 받으면서 세대주나 세대주의 배우자가 된다고 보고 묻지 않아요.
 * 이유 문장에는 사용자가 넣은 값을 넣지 않아요.
 */
public final class LoanCheck {

  /** 미성년 = 만 19세 미만 (민법 제4조). */
  private static final int ADULT_AGE = 19;

  /** 소득 상한 예외 "다자녀가구, 2자녀 가구"의 자녀 수. */
  private static final int TWO_CHILDREN = 2;

  /** 디딤돌 계열: 만 30세 미만 미혼 단독세대주는 대출 제외. */
  private static final int SINGLE_EXCLUDED_UNDER = 30;

  private final LoanTerms terms;
  private final Borrower borrower;
  private final LocalDate day;
  private final List<Verdict> verdicts = new ArrayList<>();
  private final List<String> failed = new ArrayList<>();
  private final List<String> unclear = new ArrayList<>();
  private final Set<LoanInput> missing = EnumSet.noneOf(LoanInput.class);

  private LoanCheck(LoanTerms terms, Borrower borrower, LocalDate day) {
    this.terms = terms;
    this.borrower = borrower;
    this.day = day;
  }

  /**
   * @param day 기준일 (대출접수일로 봐요). 나이·혼인 기간·출산 기간을 이날로 계산해요
   */
  public static LoanJudgment check(LoanTerms terms, Borrower borrower, LocalDate day) {
    return new LoanCheck(terms, borrower, day).run();
  }

  private LoanJudgment run() {
    if (terms.unverifiableRequirement() != null) {
      add(Part.unknown(terms.unverifiableRequirement()), null);
    }
    age();
    singleHouseholder();
    under30Single();
    add(
        borrower.homeless() == null
            ? Part.unknown("세대원 모두 무주택인지 알아야 해요", LoanInput.HOMELESS)
            : Part.of(borrower.homeless()),
        "세대원 모두 무주택이어야 해요");
    if (terms.newlywedRequired()) {
      add(newlywed(), "혼인 " + terms.newlywedMaxYears() + "년 이내 신혼부부(또는 3개월 안 결혼 예정)여야 해요");
    }
    newborn();
    if (terms.firstHomeRequired()) {
      add(firstHome(), "생애최초 주택구입(세대원 모두 집을 산 적이 없음)이어야 해요");
    }
    income();
    add(
        borrower.netAssetWon() == null
            ? Part.unknown("부부합산 순자산이 있어야 자산 조건을 볼 수 있어요", LoanInput.NET_ASSET)
            : Part.of(borrower.netAssetWon() <= terms.maxNetAssetWon()),
        "부부합산 순자산이 " + Wons.text(terms.maxNetAssetWon()) + " 이하여야 해요");
    return new LoanJudgment(terms, Eligibility.of(Verdict.all(verdicts)), failed, unclear, missing);
  }

  private void age() {
    Integer min = terms.minAge();
    Integer max = terms.maxAge();
    if (min == null && max == null) {
      return;
    }
    String range =
        min != null && max != null
            ? "만 " + min + "~" + max + "세"
            : min != null ? "만 " + min + "세 이상" : "만 " + max + "세 이하";
    if (borrower.birthDate() == null) {
      add(Part.unknown("생년월일이 있어야 나이 조건(" + range + ")을 볼 수 있어요", LoanInput.BIRTH_DATE), null);
      return;
    }
    int age = ageOf(borrower.birthDate());
    add(Part.of(within(age, min, max)), "나이가 " + range + "여야 해요");
  }

  private void singleHouseholder() {
    if (!terms.singleHouseholderRequired()) {
      return;
    }
    add(
        borrower.householdSize() == null
            ? Part.unknown("세대 가구원 수가 있어야 단독세대주인지 볼 수 있어요", LoanInput.HOUSEHOLD_SIZE)
            : Part.of(borrower.householdSize() == 1),
        "단독세대주(1인 세대)여야 해요");
  }

  /**
   * 만 30세 미만 미혼(배우자가 없는) 세대주: 혼자 사는 단독세대주는 제외, 부모·미성년 형제자매를 6개월 이상 부양하는 세대면 가능해요. 부양 기간은 묻지 않아서 확인
   * 필요로 둬요. 결혼 예정(ENGAGED)은 신혼가구로 봐서 제외하지 않아요.
   */
  private void under30Single() {
    if (!terms.under30SingleExcluded()) {
      return;
    }
    String rule = "만 " + SINGLE_EXCLUDED_UNDER + "세 미만 미혼 단독세대주는 받을 수 없어요";
    if (borrower.birthDate() == null) {
      add(Part.unknown("생년월일이 있어야 만 30세 미만 미혼세대주 제한을 볼 수 있어요", LoanInput.BIRTH_DATE), null);
      return;
    }
    if (ageOf(borrower.birthDate()) >= SINGLE_EXCLUDED_UNDER) {
      add(Part.met(), null);
      return;
    }
    MaritalStatus status = borrower.maritalStatus();
    if (status == null) {
      add(Part.unknown("혼인 상태가 있어야 만 30세 미만 미혼세대주 제한을 볼 수 있어요", LoanInput.MARITAL_STATUS), null);
      return;
    }
    if (status == MaritalStatus.MARRIED || status == MaritalStatus.ENGAGED) {
      add(Part.met(), null);
      return;
    }
    if (borrower.householdSize() == null) {
      add(Part.unknown("세대 가구원 수가 있어야 단독세대주인지 볼 수 있어요", LoanInput.HOUSEHOLD_SIZE), null);
      return;
    }
    if (borrower.householdSize() == 1) {
      add(Part.notMet(), rule);
      return;
    }
    add(Part.unknown("만 30세 미만 미혼세대주는 부모나 미성년 형제자매를 6개월 이상 부양한 세대여야 해요"), null);
  }

  /** 신혼부부: 혼인신고일부터 N년 이내 또는 결혼 예정(3개월 안이어야 하는데 날짜는 묻지 않아요). */
  private Part newlywed() {
    MaritalStatus status = borrower.maritalStatus();
    if (status == null) {
      return Part.unknown("혼인 상태가 있어야 신혼부부인지 볼 수 있어요", LoanInput.MARITAL_STATUS);
    }
    return switch (status) {
      case ENGAGED -> Part.met();
      case MARRIED ->
          borrower.marriedOn() == null
              ? Part.unknown("혼인신고일이 있어야 혼인 기간을 볼 수 있어요", LoanInput.MARRIED_ON)
              : Part.of(!borrower.marriedOn().plusYears(terms.newlywedMaxYears()).isBefore(day));
      default -> Part.notMet();
    };
  }

  private Part minors(int count) {
    List<LocalDate> births = borrower.childBirthDates();
    if (births == null) {
      return Part.unknown("자녀 생년월일이 있어야 자녀 수를 볼 수 있어요", LoanInput.CHILD_BIRTH_DATES);
    }
    long minors =
        births.stream().filter(b -> !b.isAfter(day) && b.plusYears(ADULT_AGE).isAfter(day)).count();
    return Part.of(minors >= count);
  }

  private Part firstHome() {
    return borrower.firstHomePurchase() == null
        ? Part.unknown("생애최초 주택구입인지 알아야 해요", LoanInput.FIRST_HOME_PURCHASE)
        : Part.of(borrower.firstHomePurchase());
  }

  /** 출산: 기준일부터 N개월 안에 태어난 자녀(출생일 하한 이후)가 있어야 해요. 태아는 세지 않아요. */
  private void newborn() {
    Integer months = terms.newbornWithinMonths();
    if (months == null) {
      return;
    }
    LocalDate since = terms.newbornBornSince();
    String text =
        "기준일 전 "
            + (months % 12 == 0 ? months / 12 + "년" : months + "개월")
            + " 안에 낳은 자녀가 있어야 해요"
            + (since == null ? "" : " (" + since.getYear() + "년 이후 출생)");
    List<LocalDate> births = borrower.childBirthDates();
    if (births == null) {
      add(Part.unknown("자녀 생년월일이 있어야 출산 조건을 볼 수 있어요", LoanInput.CHILD_BIRTH_DATES), null);
      return;
    }
    LocalDate from = day.minusMonths(months);
    LocalDate earliest = since != null && from.isBefore(since) ? since : from;
    add(Part.of(births.stream().anyMatch(b -> !b.isAfter(day) && !b.isBefore(earliest))), text);
  }

  /**
   * 소득: 부부합산 연소득이 기본 상한 이하면 충족. 넘으면 예외 상한(신혼가구, 2자녀 이상, 생애최초, 맞벌이, 신혼가구의 신청인 1인 소득) 중 하나라도 맞으면
   * 충족이에요.
   */
  private void income() {
    Long couple = borrower.annualIncomeWon();
    if (couple == null) {
      add(Part.unknown("부부합산 연소득이 있어야 소득 조건을 볼 수 있어요", LoanInput.ANNUAL_INCOME), null);
      return;
    }
    if (couple <= terms.maxIncomeWon()) {
      add(Part.met(), null);
      return;
    }
    List<Part> ways = new ArrayList<>();
    if (terms.maxIncomeNewlywedWon() != null && couple <= terms.maxIncomeNewlywedWon()) {
      ways.add(newlywed());
    }
    if (terms.maxIncomeTwoChildrenWon() != null && couple <= terms.maxIncomeTwoChildrenWon()) {
      ways.add(minors(TWO_CHILDREN));
    }
    if (terms.maxIncomeFirstHomeWon() != null && couple <= terms.maxIncomeFirstHomeWon()) {
      ways.add(firstHome());
    }
    if (terms.maxIncomeDualWon() != null && couple <= terms.maxIncomeDualWon()) {
      Part dual =
          borrower.dualIncome() == null
              ? Part.unknown(null, LoanInput.DUAL_INCOME)
              : Part.of(borrower.dualIncome());
      ways.add(Part.all(List.of(dual, eachWithin(couple, terms.maxEachIncomeWon()))));
    }
    if (terms.maxApplicantIncomeWon() != null) {
      Long mine = borrower.applicantAnnualIncomeWon();
      Part applicant =
          mine == null
              ? Part.unknown(null, LoanInput.APPLICANT_ANNUAL_INCOME)
              : Part.of(mine <= terms.maxApplicantIncomeWon());
      ways.add(Part.all(List.of(newlywed(), applicant)));
    }
    Part result = Part.any(ways);
    if (result.verdict() == Verdict.UNKNOWN) {
      result =
          new Part(
              Verdict.UNKNOWN,
              result.missing(),
              "부부합산 연소득이 기본 기준("
                  + Wons.text(terms.maxIncomeWon())
                  + ")을 넘어서, 다른 소득 기준에 맞는지 더 알아야 해요");
    }
    add(result, incomeRule());
  }

  /** 맞벌이 상한을 쓸 때 부부 각각의 소득 상한. 합산이 상한 이하면 각각도 이하예요. */
  private Part eachWithin(long couple, Long each) {
    if (each == null || couple <= each) {
      return Part.met();
    }
    Long mine = borrower.applicantAnnualIncomeWon();
    if (mine == null) {
      return Part.unknown(null, LoanInput.APPLICANT_ANNUAL_INCOME);
    }
    return Part.of(mine <= each && couple - mine <= each);
  }

  private String incomeRule() {
    List<String> exceptions = new ArrayList<>();
    if (terms.maxIncomeNewlywedWon() != null) {
      exceptions.add("신혼가구 " + Wons.text(terms.maxIncomeNewlywedWon()));
    }
    if (terms.maxIncomeTwoChildrenWon() != null) {
      exceptions.add("2자녀 이상 " + Wons.text(terms.maxIncomeTwoChildrenWon()));
    }
    if (terms.maxIncomeFirstHomeWon() != null) {
      exceptions.add("생애최초 " + Wons.text(terms.maxIncomeFirstHomeWon()));
    }
    if (terms.maxIncomeDualWon() != null) {
      exceptions.add("맞벌이 " + Wons.text(terms.maxIncomeDualWon()));
    }
    if (terms.maxApplicantIncomeWon() != null) {
      exceptions.add("신혼가구의 신청인 1인 소득 " + Wons.text(terms.maxApplicantIncomeWon()));
    }
    return "부부합산 연소득이 "
        + Wons.text(terms.maxIncomeWon())
        + " 이하여야 해요"
        + (exceptions.isEmpty() ? "" : " (" + String.join(", ", exceptions) + " 이하면 가능)");
  }

  private int ageOf(LocalDate birthDate) {
    return Period.between(birthDate, day).getYears();
  }

  private void add(Part part, String notMetReason) {
    verdicts.add(part.verdict());
    if (part.verdict() == Verdict.NOT_MET && notMetReason != null) {
      failed.add(notMetReason);
    }
    if (part.verdict() == Verdict.UNKNOWN) {
      if (part.reason() != null) {
        unclear.add(part.reason());
      }
      missing.addAll(part.missing());
    }
  }

  private static boolean within(int value, Integer min, Integer max) {
    return (min == null || value >= min) && (max == null || value <= max);
  }

  /** 조건 하나의 결과. 확인 필요면 이유와 필요한 입력이 붙어요. */
  private record Part(Verdict verdict, Set<LoanInput> missing, String reason) {

    static Part met() {
      return new Part(Verdict.MET, Set.of(), null);
    }

    static Part notMet() {
      return new Part(Verdict.NOT_MET, Set.of(), null);
    }

    static Part of(boolean ok) {
      return ok ? met() : notMet();
    }

    static Part unknown(String reason, LoanInput... inputs) {
      return new Part(Verdict.UNKNOWN, Set.of(inputs), reason);
    }

    static Part all(List<Part> parts) {
      return combine(Verdict.all(parts.stream().map(Part::verdict).toList()), parts);
    }

    static Part any(List<Part> parts) {
      return combine(Verdict.any(parts.stream().map(Part::verdict).toList()), parts);
    }

    private static Part combine(Verdict verdict, List<Part> parts) {
      if (verdict != Verdict.UNKNOWN) {
        return new Part(verdict, Set.of(), null);
      }
      Set<LoanInput> inputs = EnumSet.noneOf(LoanInput.class);
      String reason = null;
      for (Part part : parts) {
        if (part.verdict() == Verdict.UNKNOWN) {
          inputs.addAll(part.missing());
          reason = reason == null ? part.reason() : reason;
        }
      }
      return new Part(Verdict.UNKNOWN, inputs, reason);
    }
  }
}
