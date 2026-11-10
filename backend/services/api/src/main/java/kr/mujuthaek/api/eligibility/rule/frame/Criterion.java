package kr.mujuthaek.api.eligibility.rule.frame;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.List;

/**
 * 판정 틀의 조건 하나. 종류(kind)마다 칸이 정해져 있고, 세 틀(주거·사업공간·창업지원)이 같은 종류를 함께 써요.
 *
 * <p>어떤 틀이 어떤 종류를 쓰는지는 틀을 읽는 쪽(mapper의 FrameSpec)이 정해요. 판정 규칙은 FrameJudge와 *Rules 클래스에 있어요.
 */
public sealed interface Criterion {

  /** 모든 조건의 공통 칸. */
  Meta meta();

  default String id() {
    return meta().id();
  }

  /** 틀 JSON의 kind 값. */
  default String kind() {
    return switch (this) {
      case Age ignored -> "AGE";
      case Nationality ignored -> "NATIONALITY";
      case Residence ignored -> "RESIDENCE";
      case Region ignored -> "REGION";
      case Marriage ignored -> "MARRIAGE";
      case Children ignored -> "CHILDREN";
      case Status ignored -> "STATUS";
      case ExcludedStatus ignored -> "EXCLUDED_STATUS";
      case Homeless ignored -> "HOMELESS";
      case Income ignored -> "INCOME";
      case Asset ignored -> "ASSET";
      case Car ignored -> "CAR";
      case Savings ignored -> "SAVINGS";
      case ApplicantKind ignored -> "APPLICANT_TYPE";
      case BusinessRegistration ignored -> "BUSINESS_REGISTRATION";
      case BusinessCareer ignored -> "BUSINESS_CAREER";
      case BusinessAge ignored -> "BUSINESS_AGE";
      case BusinessAgeYears ignored -> "BUSINESS_AGE";
      case Closure ignored -> "CLOSURE";
      case Revenue ignored -> "REVENUE";
      case Industry ignored -> "INDUSTRY";
      case AnyOf ignored -> "ANY_OF";
      case Ask ignored -> "ASK";
    };
  }

  /**
   * 공통 칸.
   *
   * @param id 틀 안에서 유일한 ID. 질문(ASK)의 답도 이 ID로 받아요
   * @param quote 근거 원문
   * @param page 근거 쪽
   * @param inReview 가공하면서 확신이 없었던 조건. 계산해서 불충족이면 그대로, 아니면 확인 필요로 둬요
   * @param asOf 이 조건만 기준일이 다를 때 그 날짜 (창업지원 틀). 없으면 틀의 referenceDate
   */
  record Meta(
      String id,
      String quote,
      Integer page,
      boolean inReview,
      String reviewReason,
      LocalDate asOf) {}

  // ── 사람 ──────────────────────────────────────────────

  /** 만 나이 (예비창업자·개인은 본인, 법인은 대표자). 둘 다 포함, 한쪽은 null일 수 있어요. */
  record Age(Meta meta, Integer minAge, Integer maxAge) implements Criterion {}

  /** 국적 (ISO 두 글자). */
  record Nationality(Meta meta, List<String> countryCodes) implements Criterion {
    public Nationality {
      countryCodes = List.copyOf(countryCodes);
    }
  }

  /** 주거 틀의 거주지: 주민등록 주소가 목록 지역 안이고, minMonths가 있으면 연속 거주 개월도 비교해요. */
  record Residence(Meta meta, List<String> regionCodes, Integer minMonths) implements Criterion {
    public Residence {
      regionCodes = List.copyOf(regionCodes);
    }
  }

  /** 사업공간·창업지원 틀의 지역: 주소지나 사업장 소재지가 목록 지역 안. */
  record Region(Meta meta, RegionBasis basis, List<String> regionCodes) implements Criterion {
    public Region {
      regionCodes = List.copyOf(regionCodes);
    }
  }

  /** 혼인. NOT_MARRIED는 혼인 중이 아니면 충족, MARRIED는 혼인 중이고 혼인 기간(maxYears) 안이면 충족. */
  record Marriage(Meta meta, MarriageRequirement require, Integer maxYears, boolean allowEngaged)
      implements Criterion {}

  /** 자녀: 미성년 자녀 수(minCount)와 막내 나이(youngestMaxAge). includeUnborn이면 태아를 0세 자녀로 세요. */
  record Children(Meta meta, Integer minCount, Integer youngestMaxAge, boolean includeUnborn)
      implements Criterion {}

  /** 해당해야 하는 유형 (수급자, 소상공인, 중소기업 …). 하나라도 있으면 충족. */
  record Status(Meta meta, List<String> anyOf) implements Criterion {
    public Status {
      anyOf = List.copyOf(anyOf);
    }
  }

  /** 해당하면 안 되는 신청 제한 사유 (체납, 피후견인 …). 하나라도 있으면 불충족. */
  record ExcludedStatus(Meta meta, List<String> anyOf) implements Criterion {
    public ExcludedStatus {
      anyOf = List.copyOf(anyOf);
    }
  }

  // ── 주거 ──────────────────────────────────────────────

  /** 무주택. scope HOUSEHOLD는 세대 전원, APPLICANT는 본인. minYears가 있으면 무주택 기간도 비교해요. */
  record Homeless(Meta meta, HomelessScope scope, Integer minYears) implements Criterion {}

  /**
   * 월평균소득. 기준 금액 = 기준값 표[standard][year][가구원 수] × (percent + 가산) ÷ 100, 원 단위 반올림.
   *
   * @param standard null이면 비율 없이 금액만 적힌 공고라서 printedTable이 곧 기준 금액이에요
   * @param printedTable 공고에 찍힌 가구원 수별 금액 (기본 비율 + 가구원 수 가산). 계산과 다르면 확인 필요
   */
  record Income(
      Meta meta,
      IncomeBasis basis,
      IncomeStandard standard,
      Integer year,
      BigDecimal percent,
      List<Bonus> bonuses,
      BonusCombine bonusCombine,
      List<PrintedRow> printedTable)
      implements Criterion {
    public Income {
      bonuses = List.copyOf(bonuses);
      printedTable = List.copyOf(printedTable);
    }
  }

  /** 총자산. 한도 = maxWon과 해당하는 raisedLimits 중 가장 큰 금액. */
  record Asset(Meta meta, AssetBasis basis, long maxWon, List<RaisedLimit> raisedLimits)
      implements Criterion {
    public Asset {
      raisedLimits = List.copyOf(raisedLimits);
    }
  }

  /** 자동차가액. 한도 계산은 총자산과 같아요 (maxWon 0이면 차가 없어야 해요). */
  record Car(Meta meta, long maxWon, List<RaisedLimit> raisedLimits) implements Criterion {
    public Car {
      raisedLimits = List.copyOf(raisedLimits);
    }
  }

  /**
   * 청약통장. 적힌 기준을 모두 넘으면 충족, 모두 null이면 통장이 있기만 하면 충족.
   *
   * @param depositAreaM2 예치기준금액(주택공급에 관한 규칙 별표 2)을 쓸 때 주택의 전용면적. 넣으면 신청자 거주지와 이 면적으로 예치기준금액을 골라
   *     예치금과 비교해요 (전용 85㎡ 초과 공공건설임대·장기전세 1순위 등). minBalanceWon과 같이 쓰지 않아요
   */
  record Savings(
      Meta meta,
      Integer minMonths,
      Integer minPayments,
      Long minBalanceWon,
      BigDecimal depositAreaM2)
      implements Criterion {}

  // ── 사업 ──────────────────────────────────────────────

  /** 개인·법인 중 한쪽만 신청할 수 있을 때 (APPLICANT_TYPE). */
  record ApplicantKind(Meta meta, Applicant.ApplicantType only) implements Criterion {}

  /**
   * 사업자 등록 상태. REGISTERED는 기준일에 영업 중인 사업이 있어야, NOT_REGISTERED는 없어야 충족. CLOSED(사업공간 틀)는 영업 중인 사업이 없고
   * 기준일 전 closedWithinYears년 안에 폐업한 사업이 있어야 충족.
   */
  record BusinessRegistration(Meta meta, RegistrationRequirement require, Integer closedWithinYears)
      implements Criterion {}

  /** 영업 경력: 사업 이력의 영업 기간을 겹치지 않게 합쳐 최근 withinYears년 안의 개월 수가 minMonths 이상. */
  record BusinessCareer(Meta meta, int minMonths, Integer withinYears) implements Criterion {}

  /** 업력: 기준일에 영업 중인 사업의 개업일(법인은 설립등기일)이 openedFrom~openedTo 안 (둘 다 포함). */
  record BusinessAge(Meta meta, LocalDate openedFrom, LocalDate openedTo) implements Criterion {}

  /**
   * 업력을 기준일에서 센 햇수로만 아는 조건. 추출이 「사업을 시작한 날(법인은 설립등기일)부터 N년 이내인가요?」 같은 질문으로 준 것을 틀을 읽을 때
   * 바꿔요(FrameReader). 판정할 때 기준일로 개업일 범위를 정해 업력처럼 봐요. 날짜 정하는 법은 추출의 opened_range와 같아요: N년 이내 = N년 전
   * 같은 날~기준일, 미만 = 그다음 날부터, 이상 = ~N년 전 같은 날, 초과 = ~그 전날.
   */
  record BusinessAgeYears(Meta meta, int years, YearsRule rule) implements Criterion {

    /** 이 기준일로 정한 개업일 범위. */
    public BusinessAge on(LocalDate day) {
      LocalDate back = day.minusYears(years);
      return switch (rule) {
        case WITHIN -> new BusinessAge(meta, back, day);
        case UNDER -> new BusinessAge(meta, back.plusDays(1), day);
        case AT_LEAST -> new BusinessAge(meta, null, back);
        case OVER -> new BusinessAge(meta, null, back.minusDays(1));
      };
    }
  }

  /** 폐업 이력: 폐업일이 closedFrom~closedTo(null이면 기준일)인 사업이 NONE이면 없어야, ANY면 있어야 충족. */
  record Closure(Meta meta, ClosureMode mode, LocalDate closedFrom, LocalDate closedTo)
      implements Criterion {}

  /** 그 해 매출액이 minWon~maxWon 안 (둘 다 포함). */
  record Revenue(Meta meta, int year, Long minWon, Long maxWon) implements Criterion {}

  /**
   * 업종 (한국표준산업분류). 사용자 업종 코드(5자리)가 codes 중 하나로 시작하면 해당, maybeCodes로 시작하면 해당할 수도 있어요.
   *
   * @param revision 분류 차수 (11이 기본). 10이면 사용자 코드(11차)와 비교할 수 없어 확인 필요
   */
  record Industry(
      Meta meta, IndustryMode mode, int revision, List<String> codes, List<String> maybeCodes)
      implements Criterion {
    public Industry {
      codes = List.copyOf(codes);
      maybeCodes = List.copyOf(maybeCodes);
    }
  }

  // ── 묶음·질문 ──────────────────────────────────────────

  /** 여러 길 중 하나: options 중 하나라도 그 안 조건을 모두 충족하면 충족. */
  record AnyOf(Meta meta, List<Option> options) implements Criterion {
    public AnyOf {
      options = List.copyOf(options);
    }
  }

  /** 코드로 비교할 수 없는 조건. 사용자 답이 metWhen과 같으면 충족. */
  record Ask(Meta meta, String question, Answer metWhen) implements Criterion {}

  /** ANY_OF의 길 하나. */
  record Option(String label, List<Criterion> criteria) {
    public Option {
      criteria = List.copyOf(criteria);
    }
  }

  // ── 소득·자산의 가산·한도 완화 ─────────────────────────────

  /**
   * 가산·한도 완화가 붙는 조건. min·max는 둘 다 포함, null은 제한 없음.
   *
   * @param since NEWBORN_CHILDREN에서 이 날 이후 출생(태아 포함) 자녀를 세요
   */
  record Factor(
      FactorKind factor, Integer min, Integer max, LocalDate since, CountRule countRule) {}

  /** 소득 비율에 더할 %p. */
  record Bonus(Factor when, BigDecimal addPercent) {}

  /** 해당하면 바뀌는 자산·자동차 한도. */
  record RaisedLimit(Factor when, long maxWon) {}

  /** 공고 금액표 한 줄. */
  record PrintedRow(int householdSize, long maxWon) {}

  enum RegionBasis {
    /** 주민등록 주소지 (개인은 본인, 법인은 대표자). */
    RESIDENCE,
    /** 사업장(본점) 소재지. */
    BUSINESS_SITE,
    /** 둘 중 하나. */
    RESIDENCE_OR_BUSINESS_SITE
  }

  enum MarriageRequirement {
    MARRIED,
    NOT_MARRIED
  }

  enum HomelessScope {
    HOUSEHOLD,
    APPLICANT
  }

  /** 누구 소득을 몇 인 기준으로. */
  enum IncomeBasis {
    /** 세대 월소득, 세대 가구원 수. */
    HOUSEHOLD,
    /** 본인 월소득, 1인. */
    APPLICANT,
    /** 본인 + 부모 월소득 합, 본인과 부모의 가구원 수. */
    APPLICANT_AND_PARENTS,
    /** 세대주면 세대 기준, 세대원이면 본인 기준. */
    HOUSEHOLD_IF_HEAD
  }

  /** 소득 기준표. 기준값(4-08) 표의 종류와 같아요. */
  enum IncomeStandard {
    MEDIAN_INCOME,
    URBAN_WORKER_INCOME,
    URBAN_WORKER_AVERAGE_INCOME
  }

  enum BonusCombine {
    /** 해당하는 가산을 모두 더해요. */
    SUM,
    /** 해당하는 가산 중 가장 큰 것 하나. */
    MAX
  }

  enum AssetBasis {
    HOUSEHOLD,
    APPLICANT
  }

  enum FactorKind {
    /** 소득 기준에 쓰는 가구원 수. */
    HOUSEHOLD_SIZE,
    /** since 이후 출생(태아 포함) 자녀 수. */
    NEWBORN_CHILDREN,
    /** 미성년 자녀 수 (태아 포함). */
    CHILDREN,
    /** 맞벌이. */
    DUAL_INCOME
  }

  /** 출생 자녀 세는 방법. */
  enum CountRule {
    /** since 이후 출생 자녀가 1명이라도 있으면, 그 전에 태어난 미성년 자녀까지 함께 세요. */
    MINORS_IF_ANY_SINCE,
    /** since 이후 출생 자녀만 세요. */
    BORN_SINCE_ONLY
  }

  enum RegistrationRequirement {
    REGISTERED,
    NOT_REGISTERED,
    CLOSED
  }

  enum YearsRule {
    /** N년 이내 (N년 전 같은 날 포함). */
    WITHIN,
    /** N년이 지나지 않음 (미만). */
    UNDER,
    /** N년 이상 지남. */
    AT_LEAST,
    /** N년이 넘게 지남 (초과). */
    OVER
  }

  enum ClosureMode {
    /** 그 기간에 폐업한 사업이 없어야 해요. */
    NONE,
    /** 그 기간에 폐업한 사업이 있어야 해요. */
    ANY
  }

  enum IndustryMode {
    /** 제한 업종: 해당하면 불충족. */
    EXCLUDE,
    /** 대상 업종: 해당해야 충족. */
    ONLY
  }
}
