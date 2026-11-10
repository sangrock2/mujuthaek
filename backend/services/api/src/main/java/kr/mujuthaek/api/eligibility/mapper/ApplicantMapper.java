package kr.mujuthaek.api.eligibility.mapper;

import java.time.LocalDate;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.function.Predicate;
import kr.mujuthaek.api.common.exception.CustomException;
import kr.mujuthaek.api.common.exception.ErrorCode;
import kr.mujuthaek.api.eligibility.dto.request.JudgmentApplicantRequest;
import kr.mujuthaek.api.eligibility.dto.request.JudgmentApplicantRequest.BusinessRecordRequest;
import kr.mujuthaek.api.eligibility.rule.frame.Answer;
import kr.mujuthaek.api.eligibility.rule.frame.Applicant;
import kr.mujuthaek.api.eligibility.rule.frame.Codes;
import kr.mujuthaek.api.eligibility.rule.frame.RegionCodes;

/** 사용자 입력 요청 → 판정 모델. 형식이 틀린 값은 400으로 알려주되, 오류 메시지에 사용자가 넣은 값은 넣지 않아요 (소득·자산·나이 보호). */
public final class ApplicantMapper {

  private ApplicantMapper() {}

  public static Applicant toApplicant(
      JudgmentApplicantRequest request, Map<String, Answer> answers) {
    if (request == null) {
      return new Applicant(
          null, null, null, null, null, null, null, null, null, null, null, null, null, answers);
    }
    checkRegion(request.residenceRegionCode(), "profile.residenceRegionCode");
    checkAtLeast(request.residenceMonths(), 0, "profile.residenceMonths");
    if (request.childBirthDates() != null) {
      check(
          request.childBirthDates().stream().allMatch(d -> d != null),
          "profile.childBirthDates",
          "빈 날짜가 있어요");
    }
    return new Applicant(
        request.birthDate(),
        request.korean(),
        request.residenceRegionCode(),
        request.residenceMonths(),
        request.maritalStatus(),
        request.marriedOn(),
        request.childBirthDates(),
        request.expectingChild(),
        household(request.household()),
        subscription(request.subscription()),
        business(request.business()),
        codes(request.statuses(), Codes::isStatus, "profile.statuses", "유형"),
        codes(request.restrictions(), Codes::isRestriction, "profile.restrictions", "신청 제한 사유"),
        answers,
        request.birthMonth());
  }

  private static Applicant.Household household(JudgmentApplicantRequest.HouseholdRequest h) {
    if (h == null) {
      return null;
    }
    checkAtLeast(h.size(), 1, "profile.household.size");
    checkAtLeast(h.homelessYears(), 0, "profile.household.homelessYears");
    checkAtLeast(h.monthlyIncomeWon(), 0, "profile.household.monthlyIncomeWon");
    checkAtLeast(h.applicantMonthlyIncomeWon(), 0, "profile.household.applicantMonthlyIncomeWon");
    checkAtLeast(h.parentsMonthlyIncomeWon(), 0, "profile.household.parentsMonthlyIncomeWon");
    checkAtLeast(h.applicantAndParentsSize(), 1, "profile.household.applicantAndParentsSize");
    checkAtLeast(h.carValueWon(), 0, "profile.household.carValueWon");
    return new Applicant.Household(
        h.size(),
        h.head(),
        h.homeless(),
        h.applicantHomeless(),
        h.homelessYears(),
        h.monthlyIncomeWon(),
        h.applicantMonthlyIncomeWon(),
        h.parentsMonthlyIncomeWon(),
        h.applicantAndParentsSize(),
        h.dualIncome(),
        h.totalAssetWon(),
        h.applicantTotalAssetWon(),
        h.carValueWon());
  }

  private static Applicant.Subscription subscription(
      JudgmentApplicantRequest.SubscriptionRequest s) {
    if (s == null) {
      return null;
    }
    checkAtLeast(s.months(), 0, "profile.subscription.months");
    checkAtLeast(s.payments(), 0, "profile.subscription.payments");
    checkAtLeast(s.balanceWon(), 0, "profile.subscription.balanceWon");
    return new Applicant.Subscription(s.months(), s.payments(), s.balanceWon());
  }

  private static Applicant.Business business(JudgmentApplicantRequest.BusinessRequest b) {
    if (b == null) {
      return null;
    }
    checkRegion(b.siteRegionCode(), "profile.business.siteRegionCode");
    check(
        b.industryCode() == null || b.industryCode().matches("\\d{5}"),
        "profile.business.industryCode",
        "업종 코드는 한국표준산업분류 11차 5자리 숫자예요");
    List<Applicant.BusinessRecord> history = null;
    if (b.history() != null) {
      history = b.history().stream().map(ApplicantMapper::record).toList();
    }
    if (b.revenueByYear() != null) {
      check(
          b.revenueByYear().values().stream().allMatch(v -> v != null),
          "profile.business.revenueByYear",
          "빈 매출액이 있어요");
    }
    return new Applicant.Business(
        b.applicantType(),
        b.hasSite(),
        b.siteRegionCode(),
        history,
        b.industryCode(),
        b.revenueByYear());
  }

  private static Applicant.BusinessRecord record(BusinessRecordRequest r) {
    check(r != null && r.openedOn() != null, "profile.business.history", "개업일이 있어야 해요");
    LocalDate closed = r.closedOn();
    check(
        closed == null || !closed.isBefore(r.openedOn()),
        "profile.business.history",
        "폐업일이 개업일보다 앞이에요");
    return new Applicant.BusinessRecord(r.openedOn(), closed);
  }

  private static Set<String> codes(
      List<String> codes, Predicate<String> known, String at, String what) {
    if (codes == null) {
      return null;
    }
    Set<String> result = new HashSet<>();
    for (String code : codes) {
      check(code != null && known.test(code), at, "모르는 " + what + " 코드가 있어요");
      result.add(code);
    }
    return result;
  }

  private static void checkRegion(String code, String at) {
    check(code == null || RegionCodes.valid(code), at, "법정동코드는 2·5·8·10자리 숫자예요");
  }

  private static void checkAtLeast(Number value, long min, String at) {
    check(value == null || value.longValue() >= min, at, min + " 이상이어야 해요");
  }

  private static void check(boolean ok, String at, String problem) {
    if (!ok) {
      throw new CustomException(ErrorCode.VALIDATION_FAILED, at + ": " + problem);
    }
  }
}
