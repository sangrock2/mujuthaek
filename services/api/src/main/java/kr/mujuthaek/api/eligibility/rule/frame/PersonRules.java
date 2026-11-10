package kr.mujuthaek.api.eligibility.rule.frame;

import java.time.LocalDate;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import kr.mujuthaek.api.eligibility.rule.Bands;
import kr.mujuthaek.api.eligibility.rule.Verdict;
import kr.mujuthaek.api.eligibility.rule.frame.Applicant.MaritalStatus;
import kr.mujuthaek.api.eligibility.rule.frame.Criterion.Age;
import kr.mujuthaek.api.eligibility.rule.frame.Criterion.Ask;
import kr.mujuthaek.api.eligibility.rule.frame.Criterion.Children;
import kr.mujuthaek.api.eligibility.rule.frame.Criterion.ExcludedStatus;
import kr.mujuthaek.api.eligibility.rule.frame.Criterion.Marriage;
import kr.mujuthaek.api.eligibility.rule.frame.Criterion.Nationality;
import kr.mujuthaek.api.eligibility.rule.frame.Criterion.Region;
import kr.mujuthaek.api.eligibility.rule.frame.Criterion.Residence;
import kr.mujuthaek.api.eligibility.rule.frame.Criterion.Status;

/** 사람에 대한 조건: 나이, 국적, 거주지·지역, 혼인, 자녀, 유형, 신청 제한 사유, 질문. */
final class PersonRules {

  /** 대한민국 국가 코드 (ISO 3166-1). */
  private static final String KOREA = "KR";

  private PersonRules() {}

  static Evaluation age(Age c, Applicant a, LocalDate on) {
    String summary = Texts.ageRange(c.minAge(), c.maxAge());
    if (a.birthDate() == null && a.birthMonth() != null) {
      // 출생 연월만 알면 그 달의 첫날·마지막 날 둘 다 같은 결과일 때만 정해요 (기준일이 생일 달이면 확인 필요). 출생 연월만 보내던 예전 화면이라
      // 생년월일을 더 묻지 않고 주거 판정과 같은 문구로 둬요 (2026-10-29 QA). 지금 화면은 생년월일을 보내요(2026-11-01)
      var status = Bands.ageWithin(Bands.ages(a.birthMonth(), on), c.minAge(), c.maxAge());
      return status == kr.mujuthaek.api.eligibility.rule.Status.UNKNOWN
          ? Evaluation.unknown(c, summary, "생일이 지났는지에 따라 달라져요. 직접 확인해 주세요")
          : Evaluation.decided(c, status == kr.mujuthaek.api.eligibility.rule.Status.MET, summary);
    }
    if (a.birthDate() == null) {
      return Evaluation.unknown(c, summary, "생년월일이 없어요", Input.BIRTH_DATE);
    }
    int age = Ages.on(a.birthDate(), on);
    boolean met =
        (c.minAge() == null || age >= c.minAge()) && (c.maxAge() == null || age <= c.maxAge());
    return Evaluation.decided(c, met, summary);
  }

  /** 국적: 사용자에게는 대한민국 국민인지만 받아요. 틀이 KR만 받으면 국민이 아닐 때 불충족이고, 다른 나라 국적도 받으면 어느 나라인지 몰라서 확인 필요예요. */
  static Evaluation nationality(Nationality c, Applicant a) {
    String summary = "국적: " + Texts.codes(c.countryCodes());
    if (a.korean() == null) {
      return Evaluation.unknown(c, summary, "대한민국 국민인지 답이 없어요", Input.KOREAN);
    }
    if (a.korean()) {
      return Evaluation.decided(c, c.countryCodes().contains(KOREA), summary);
    }
    if (c.countryCodes().stream().allMatch(KOREA::equals)) {
      return Evaluation.notMet(c, summary, null);
    }
    return Evaluation.unknown(c, summary, "대한민국 국민이 아니라서 어느 나라 국적인지 확인이 필요해요");
  }

  /** 주거 틀의 거주지: 지역이 맞고, minMonths가 있으면 연속 거주 개월도 넘어야 해요. */
  static Evaluation residence(Residence c, Applicant a) {
    String summary =
        "주민등록 주소가 "
            + Texts.codes(c.regionCodes())
            + " 지역 안"
            + (c.minMonths() == null ? "" : ", 연속 거주 " + c.minMonths() + "개월 이상");
    Evaluation place = residencePlace(c, summary, a, c.regionCodes());
    if (place.verdict() != Verdict.MET || c.minMonths() == null) {
      return place;
    }
    if (a.residenceMonths() == null) {
      return Evaluation.unknown(c, summary, "연속 거주 개월이 없어요", Input.RESIDENCE_MONTHS);
    }
    return Evaluation.decided(c, a.residenceMonths() >= c.minMonths(), summary);
  }

  /** 사업공간·창업지원 틀의 지역: 주소지, 사업장 소재지, 또는 둘 중 하나. */
  static Evaluation region(Region c, Applicant a) {
    String place =
        switch (c.basis()) {
          case RESIDENCE -> "주민등록 주소가 ";
          case BUSINESS_SITE -> "사업장 소재지가 ";
          case RESIDENCE_OR_BUSINESS_SITE -> "주민등록 주소나 사업장 소재지가 ";
        };
    String summary = place + Texts.codes(c.regionCodes()) + " 지역 안";
    return switch (c.basis()) {
      case RESIDENCE -> residencePlace(c, summary, a, c.regionCodes());
      case BUSINESS_SITE -> sitePlace(c, summary, a, c.regionCodes());
      case RESIDENCE_OR_BUSINESS_SITE -> {
        Evaluation home = residencePlace(c, summary, a, c.regionCodes());
        Evaluation site = sitePlace(c, summary, a, c.regionCodes());
        Verdict either = Verdict.any(List.of(home.verdict(), site.verdict()));
        if (either == Verdict.UNKNOWN) {
          Set<Input> missing = new LinkedHashSet<>(home.missing());
          missing.addAll(site.missing());
          yield Evaluation.unknown(c, summary, "주소지나 사업장 소재지를 더 넣어야 알 수 있어요", missing);
        }
        yield Evaluation.decided(c, either == Verdict.MET, summary);
      }
    };
  }

  private static Evaluation residencePlace(
      Criterion c, String summary, Applicant a, List<String> codes) {
    if (a.residenceRegionCode() == null) {
      return Evaluation.unknown(c, summary, "주민등록 주소지가 없어요", Input.RESIDENCE_REGION);
    }
    Verdict verdict = RegionCodes.withinAny(a.residenceRegionCode(), codes);
    if (verdict == Verdict.UNKNOWN) {
      return Evaluation.unknown(
          c, summary, "공고 지역에 드는지 알려면 주소지를 더 자세히(구·읍면동까지) 넣어야 해요", Input.RESIDENCE_REGION);
    }
    return Evaluation.decided(c, verdict == Verdict.MET, summary);
  }

  private static Evaluation sitePlace(
      Criterion c, String summary, Applicant a, List<String> codes) {
    Applicant.Business business = a.business();
    if (Boolean.FALSE.equals(business.hasSite())) {
      return Evaluation.notMet(c, summary, "사업장이 없어요");
    }
    if (business.siteRegionCode() == null) {
      return Evaluation.unknown(c, summary, "사업장 소재지가 없어요", Input.BUSINESS_SITE);
    }
    Verdict verdict = RegionCodes.withinAny(business.siteRegionCode(), codes);
    if (verdict == Verdict.UNKNOWN) {
      return Evaluation.unknown(
          c, summary, "공고 지역에 드는지 알려면 사업장 소재지를 더 자세히(구·읍면동까지) 넣어야 해요", Input.BUSINESS_SITE);
    }
    return Evaluation.decided(c, verdict == Verdict.MET, summary);
  }

  static Evaluation marriage(Marriage c, Applicant a, LocalDate on) {
    String summary =
        switch (c.require()) {
          case NOT_MARRIED -> "혼인 중이 아님";
          case MARRIED ->
              "혼인 중"
                  + (c.maxYears() == null ? "" : " (혼인 " + c.maxYears() + "년 이내)")
                  + (c.allowEngaged() ? ", 예비신혼부부 포함" : "");
        };
    MaritalStatus status = a.maritalStatus();
    if (status == null) {
      return Evaluation.unknown(c, summary, "혼인 상태가 없어요", Input.MARITAL_STATUS);
    }
    if (c.require() == Criterion.MarriageRequirement.NOT_MARRIED) {
      return Evaluation.decided(c, status != MaritalStatus.MARRIED, summary);
    }
    if (status == MaritalStatus.ENGAGED) {
      return Evaluation.decided(c, c.allowEngaged(), summary);
    }
    if (status != MaritalStatus.MARRIED) {
      return Evaluation.notMet(c, summary, null);
    }
    if (c.maxYears() == null) {
      return Evaluation.met(c, summary);
    }
    if (a.marriedOn() == null) {
      return Evaluation.unknown(c, summary, "혼인신고일이 없어요", Input.MARRIED_ON);
    }
    return Evaluation.decided(c, !a.marriedOn().plusYears(c.maxYears()).isBefore(on), summary);
  }

  static Evaluation children(Children c, Applicant a, LocalDate on) {
    List<String> parts = new ArrayList<>();
    if (c.minCount() != null) {
      parts.add("미성년 자녀 " + c.minCount() + "명 이상");
    }
    if (c.youngestMaxAge() != null) {
      parts.add("막내 만 " + c.youngestMaxAge() + "세 이하");
    }
    String summary = String.join(", ", parts) + (c.includeUnborn() ? " (태아 포함)" : "");
    List<LocalDate> births = a.childBirthDates();
    if (births == null) {
      return Evaluation.unknown(c, summary, "자녀 생년월일이 없어요 (없으면 빈 목록)", Input.CHILD_BIRTH_DATES);
    }
    if (!c.includeUnborn() || a.expectingChild() != null) {
      boolean unborn = c.includeUnborn() && a.expectingChild();
      return Evaluation.decided(c, childrenMet(c, births, on, unborn), summary);
    }
    boolean without = childrenMet(c, births, on, false);
    boolean with = childrenMet(c, births, on, true);
    if (without == with) {
      return Evaluation.decided(c, without, summary);
    }
    return Evaluation.unknown(c, summary, "임신 중인지에 따라 결과가 달라져요", Input.EXPECTING_CHILD);
  }

  private static boolean childrenMet(
      Children c, List<LocalDate> births, LocalDate on, boolean unborn) {
    boolean countMet = c.minCount() == null || Kids.minors(births, on, unborn) >= c.minCount();
    if (c.youngestMaxAge() == null) {
      return countMet;
    }
    Integer youngest = Kids.youngestAge(births, on, unborn);
    return countMet && youngest != null && youngest <= c.youngestMaxAge();
  }

  static Evaluation status(Status c, Applicant a) {
    String summary = "해당 유형: " + Texts.labels(c.anyOf());
    if (a.statuses() == null) {
      return Evaluation.unknown(c, summary, "유형을 아직 고르지 않았어요", Input.STATUSES);
    }
    return Evaluation.decided(c, c.anyOf().stream().anyMatch(a.statuses()::contains), summary);
  }

  static Evaluation excludedStatus(ExcludedStatus c, Applicant a) {
    String summary = "해당하면 안 돼요: " + Texts.labels(c.anyOf());
    if (a.restrictions() == null) {
      return Evaluation.unknown(c, summary, "신청 제한 사유를 아직 고르지 않았어요", Input.RESTRICTIONS);
    }
    if (c.anyOf().stream().anyMatch(a.restrictions()::contains)) {
      return Evaluation.notMet(c, summary, "고른 신청 제한 사유에 해당해요");
    }
    return Evaluation.met(c, summary);
  }

  static Evaluation ask(Ask c, Applicant a) {
    Answer answer = a.answers().get(c.id());
    if (answer == null) {
      // 화면은 공고마다 묻는 예/아니요 답을 보내지 않아요 (2026-10-29 결정). 드문 조건이라 원문을 보게 해요
      return Evaluation.unknown(c, c.question(), "원문 조건을 확인해 주세요");
    }
    return Evaluation.decided(c, answer == c.metWhen(), c.question());
  }
}
