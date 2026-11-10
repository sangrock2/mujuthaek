package kr.mujuthaek.api.eligibility.rule.frame;

import java.time.LocalDate;
import java.util.List;
import kr.mujuthaek.api.eligibility.rule.frame.Applicant.BusinessRecord;
import kr.mujuthaek.api.eligibility.rule.frame.Criterion.ApplicantKind;
import kr.mujuthaek.api.eligibility.rule.frame.Criterion.BusinessAge;
import kr.mujuthaek.api.eligibility.rule.frame.Criterion.BusinessAgeYears;
import kr.mujuthaek.api.eligibility.rule.frame.Criterion.BusinessCareer;
import kr.mujuthaek.api.eligibility.rule.frame.Criterion.BusinessRegistration;
import kr.mujuthaek.api.eligibility.rule.frame.Criterion.Closure;
import kr.mujuthaek.api.eligibility.rule.frame.Criterion.Industry;
import kr.mujuthaek.api.eligibility.rule.frame.Criterion.IndustryMode;
import kr.mujuthaek.api.eligibility.rule.frame.Criterion.Revenue;

/** 사업 조건: 개인·법인, 사업자 등록 상태, 영업 경력, 업력, 폐업 이력, 매출, 업종. 사업 이력(개업일·폐업일)으로 계산해요. */
final class BusinessRules {

  private BusinessRules() {}

  static Evaluation applicantKind(ApplicantKind c, Applicant a) {
    String summary = c.only() == Applicant.ApplicantType.INDIVIDUAL ? "개인만 신청" : "법인만 신청";
    if (a.business().applicantType() == null) {
      return Evaluation.unknown(c, summary, "신청 형태(개인·법인)가 없어요", Input.APPLICANT_TYPE);
    }
    return Evaluation.decided(c, a.business().applicantType() == c.only(), summary);
  }

  static Evaluation registration(BusinessRegistration c, Applicant a, LocalDate on) {
    String summary =
        switch (c.require()) {
          case REGISTERED -> "기준일(" + on + ")에 영업 중인 사업자";
          case NOT_REGISTERED -> "예비창업자 (기준일 " + on + "에 영업 중인 사업 없음)";
          case CLOSED ->
              "영업 중인 사업 없이 "
                  + (c.closedWithinYears() == null
                      ? "폐업한 적 있음"
                      : "최근 " + c.closedWithinYears() + "년 안에 폐업");
        };
    List<BusinessRecord> history = a.business().history();
    if (history == null) {
      return Evaluation.unknown(c, summary, "사업 이력이 없어요 (사업이 없으면 빈 목록)", Input.BUSINESS_HISTORY);
    }
    boolean operating = !BusinessHistory.operating(history, on).isEmpty();
    return switch (c.require()) {
      case REGISTERED -> Evaluation.decided(c, operating, summary);
      case NOT_REGISTERED -> Evaluation.decided(c, !operating, summary);
      case CLOSED -> {
        LocalDate from =
            c.closedWithinYears() == null ? LocalDate.MIN : on.minusYears(c.closedWithinYears());
        yield Evaluation.decided(
            c, !operating && BusinessHistory.closedBetween(history, from, on), summary);
      }
    };
  }

  static Evaluation career(BusinessCareer c, Applicant a, LocalDate on) {
    String summary =
        (c.withinYears() == null ? "" : "최근 " + c.withinYears() + "년 ")
            + "영업경력 "
            + c.minMonths()
            + "개월 이상 (폐업한 사업 포함)";
    List<BusinessRecord> history = a.business().history();
    if (history == null) {
      return Evaluation.unknown(c, summary, "사업 이력이 없어요 (사업이 없으면 빈 목록)", Input.BUSINESS_HISTORY);
    }
    return Evaluation.decided(
        c, BusinessHistory.careerMonths(history, on, c.withinYears()) >= c.minMonths(), summary);
  }

  static Evaluation age(BusinessAge c, Applicant a, LocalDate on) {
    String summary;
    if (c.openedFrom() != null && c.openedTo() != null) {
      summary = "개업일 " + c.openedFrom() + " ~ " + c.openedTo() + " (둘 다 포함)";
    } else if (c.openedFrom() != null) {
      summary = "개업일 " + c.openedFrom() + " 이후 (같은 날 포함)";
    } else {
      summary = "개업일 " + c.openedTo() + " 이전 (같은 날 포함)";
    }
    List<BusinessRecord> history = a.business().history();
    if (history == null) {
      return Evaluation.unknown(c, summary, "사업 이력이 없어요 (사업이 없으면 빈 목록)", Input.BUSINESS_HISTORY);
    }
    List<BusinessRecord> now = BusinessHistory.operating(history, on);
    if (now.isEmpty()) {
      return Evaluation.notMet(c, summary, "기준일(" + on + ")에 영업 중인 사업이 없어요");
    }
    if (now.size() > 1) {
      return Evaluation.unknown(c, summary, "영업 중인 사업이 둘 이상이라 어느 사업의 업력인지 확인이 필요해요");
    }
    LocalDate opened = now.getFirst().openedOn();
    boolean met =
        (c.openedFrom() == null || !opened.isBefore(c.openedFrom()))
            && (c.openedTo() == null || !opened.isAfter(c.openedTo()));
    return Evaluation.decided(c, met, summary);
  }

  /** 업력 햇수: 기준일로 개업일 범위를 정해 업력처럼 보고, 설명 앞에 공고의 햇수를 붙여요 (예: 창업 7년 이내 · 개업일 …). */
  static Evaluation ageInYears(BusinessAgeYears c, Applicant a, LocalDate on) {
    Evaluation e = age(c.on(on), a, on);
    String rule =
        switch (c.rule()) {
          case WITHIN -> "이내";
          case UNDER -> "미만";
          case AT_LEAST -> "이상";
          case OVER -> "초과";
        };
    return new Evaluation(
        c,
        e.verdict(),
        "창업 " + c.years() + "년 " + rule + " · " + e.summary(),
        e.reason(),
        e.missing(),
        e.options());
  }

  static Evaluation closure(Closure c, Applicant a, LocalDate on) {
    LocalDate to = c.closedTo() == null ? on : c.closedTo();
    String period = c.closedFrom() == null ? to + "까지" : c.closedFrom() + " ~ " + to;
    String summary =
        c.mode() == Criterion.ClosureMode.NONE
            ? period + "에 폐업한 사업이 없어야 해요"
            : period + "에 폐업한 사업이 있어야 해요";
    List<BusinessRecord> history = a.business().history();
    if (history == null) {
      return Evaluation.unknown(c, summary, "사업 이력이 없어요 (사업이 없으면 빈 목록)", Input.BUSINESS_HISTORY);
    }
    LocalDate from = c.closedFrom() == null ? LocalDate.MIN : c.closedFrom();
    boolean closed = BusinessHistory.closedBetween(history, from, to);
    return Evaluation.decided(
        c, c.mode() == Criterion.ClosureMode.NONE ? !closed : closed, summary);
  }

  static Evaluation revenue(Revenue c, Applicant a) {
    String range;
    if (c.minWon() != null && c.maxWon() != null) {
      range = Texts.won(c.minWon()) + " ~ " + Texts.won(c.maxWon());
    } else if (c.maxWon() != null) {
      range = Texts.won(c.maxWon()) + " 이하";
    } else {
      range = Texts.won(c.minWon()) + " 이상";
    }
    String summary = c.year() + "년 매출액 " + range;
    var byYear = a.business().revenueByYear();
    Long revenue = byYear == null ? null : byYear.get(c.year());
    if (revenue == null) {
      return Evaluation.unknown(c, summary, c.year() + "년 매출액이 없어요", Input.REVENUE);
    }
    boolean met =
        (c.minWon() == null || revenue >= c.minWon())
            && (c.maxWon() == null || revenue <= c.maxWon());
    return Evaluation.decided(c, met, summary);
  }

  static Evaluation industry(Industry c, Applicant a) {
    String summary =
        (c.mode() == IndustryMode.EXCLUDE ? "제한 업종: " : "대상 업종: ")
            + Texts.codes(c.codes())
            + (c.maybeCodes().isEmpty() ? "" : " (해당할 수도: " + Texts.codes(c.maybeCodes()) + ")")
            + " — 한국표준산업분류 "
            + c.revision()
            + "차";
    String code = a.business().industryCode();
    if (code == null) {
      return Evaluation.unknown(c, summary, "업종 코드가 없어요", Input.INDUSTRY);
    }
    if (c.revision() != 11) {
      return Evaluation.unknown(
          c, summary, "공고가 한국표준산업분류 " + c.revision() + "차 기준이라 11차 업종 코드와 바로 비교할 수 없어요");
    }
    boolean hit = c.codes().stream().anyMatch(code::startsWith);
    boolean maybe = c.maybeCodes().stream().anyMatch(code::startsWith);
    if (c.mode() == IndustryMode.EXCLUDE) {
      if (hit) {
        return Evaluation.notMet(c, summary, "제한 업종이에요");
      }
      return maybe
          ? Evaluation.unknown(c, summary, "제한 업종에 해당할 수도 있어서 확인이 필요해요")
          : Evaluation.met(c, summary);
    }
    if (hit) {
      return Evaluation.met(c, summary);
    }
    return maybe
        ? Evaluation.unknown(c, summary, "대상 업종에 해당할 수도 있어서 확인이 필요해요")
        : Evaluation.notMet(c, summary, "대상 업종이 아니에요");
  }
}
