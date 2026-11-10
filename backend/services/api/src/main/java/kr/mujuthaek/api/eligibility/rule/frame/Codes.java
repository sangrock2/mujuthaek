package kr.mujuthaek.api.eligibility.rule.frame;

import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;

/**
 * 유형(STATUS)·신청 제한 사유(EXCLUDED_STATUS) 코드와 이름. 사용자는 이 코드 중에서 골라요.
 *
 * <p>분야마다 틀이 쓸 수 있는 코드가 달라요. 같은 코드는 분야가 달라도 뜻이 같아요 (예: TAX_ARREARS).
 */
public final class Codes {

  /** 주거 틀의 유형. */
  public static final Map<String, String> HOUSING_STATUSES =
      ordered(
          "LIVELIHOOD_BENEFIT", "생계급여 수급자",
          "MEDICAL_BENEFIT", "의료급여 수급자",
          "HOUSING_BENEFIT", "주거급여 수급자",
          "EDUCATION_BENEFIT", "교육급여 수급자",
          "NEAR_POOR", "차상위계층",
          "SINGLE_PARENT", "한부모가족",
          "DISABLED", "장애인",
          "NATIONAL_MERIT", "국가유공자 등 보훈대상자",
          "NORTH_KOREAN_DEFECTOR", "북한이탈주민",
          "FACILITY_LEAVER", "보호종료아동·시설퇴소자",
          "UNIVERSITY_STUDENT", "대학생",
          "JOB_SEEKER", "취업준비생");

  /** 사업공간 틀의 유형. */
  public static final Map<String, String> BUSINESS_SPACE_STATUSES =
      ordered(
          "SMALL_BUSINESS", "소상공인",
          "CAREER_BREAK_WOMAN", "경력단절여성",
          "SOCIAL_ENTERPRISE", "사회적기업",
          "PRE_SOCIAL_ENTERPRISE", "예비사회적기업",
          "SOCIAL_COOPERATIVE", "사회적협동조합",
          "VILLAGE_ENTERPRISE", "마을기업",
          "SELF_SUFFICIENCY_ENTERPRISE", "자활기업",
          "SOCIAL_VENTURE", "소셜벤처",
          "NATIONAL_MERIT", "국가유공자 등 보훈대상자");

  /** 창업지원 틀의 유형. */
  public static final Map<String, String> STARTUP_SUPPORT_STATUSES =
      ordered(
          "SME", "중소기업",
          "WOMAN", "여성",
          "SMALL_BUSINESS", "소상공인",
          "VENTURE_COMPANY", "벤처기업",
          "SOCIAL_VENTURE", "소셜벤처",
          "DISABLED", "장애인",
          "ONE_PERSON_CREATIVE", "1인 창조기업",
          "STUDENT", "대학생·대학원생");

  /** 사업공간 틀의 신청 제한 사유. */
  public static final Map<String, String> BUSINESS_SPACE_RESTRICTIONS =
      ordered(
          "ADULT_WARD", "피성년후견인·피한정후견인",
          "LH_EMPLOYEE_FAMILY", "LH 직원과 그 배우자·부모·자녀",
          "TAX_ARREARS", "국세·지방세 체납 중",
          "CREDIT_DELINQUENT", "금융기관 채무불이행·불량거래자",
          "BUSINESS_SUSPENDED", "휴업 중인 사업자");

  /** 창업지원 틀의 신청 제한 사유. */
  public static final Map<String, String> STARTUP_SUPPORT_RESTRICTIONS =
      ordered(
          "CREDIT_DELINQUENT", "금융기관 채무불이행·불량거래자",
          "TAX_ARREARS", "국세·지방세 체납 중",
          "CLAWBACK_UNPAID", "환수금 반환이 끝나지 않음",
          "PROGRAM_SANCTION", "창업지원사업 참여 제한 제재 중",
          "BUSINESS_SUSPENDED", "휴업 중인 사업자",
          "WAGE_ARREARS", "체불사업주 명단 공개 대상",
          "SUBSIDY_EXCLUDED", "보조사업 수행 배제 대상");

  private static final Map<String, String> ALL = new LinkedHashMap<>();

  static {
    ALL.putAll(HOUSING_STATUSES);
    ALL.putAll(BUSINESS_SPACE_STATUSES);
    ALL.putAll(STARTUP_SUPPORT_STATUSES);
    ALL.putAll(BUSINESS_SPACE_RESTRICTIONS);
    ALL.putAll(STARTUP_SUPPORT_RESTRICTIONS);
  }

  private Codes() {}

  /** 사용자가 고를 수 있는 모든 유형 코드 (세 분야 합). */
  public static boolean isStatus(String code) {
    return HOUSING_STATUSES.containsKey(code)
        || BUSINESS_SPACE_STATUSES.containsKey(code)
        || STARTUP_SUPPORT_STATUSES.containsKey(code);
  }

  /** 사용자가 고를 수 있는 모든 신청 제한 사유 코드 (두 분야 합). */
  public static boolean isRestriction(String code) {
    return BUSINESS_SPACE_RESTRICTIONS.containsKey(code)
        || STARTUP_SUPPORT_RESTRICTIONS.containsKey(code);
  }

  static String label(String code) {
    return ALL.getOrDefault(code, code);
  }

  private static Map<String, String> ordered(String... pairs) {
    Map<String, String> map = new LinkedHashMap<>();
    for (int i = 0; i < pairs.length; i += 2) {
      map.put(pairs[i], pairs[i + 1]);
    }
    return Collections.unmodifiableMap(map);
  }
}
