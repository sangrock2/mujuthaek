package kr.mujuthaek.api.eligibility.mapper;

import java.util.EnumSet;
import java.util.Set;
import kr.mujuthaek.api.eligibility.rule.Field;
import kr.mujuthaek.api.eligibility.rule.frame.Codes;
import kr.mujuthaek.api.eligibility.rule.frame.Criterion.RegistrationRequirement;

/**
 * 분야별 판정 틀 형식: 어떤 조건 종류와 코드를 쓸 수 있는지. 판정 틀 정의서(JSON Schema)와 같아요.
 *
 * @param sourceIdField 가공한 공고를 가리키는 칸 (주거·사업공간 rawPostId, 창업지원 rawPolicyId)
 * @param preferences 우대(preferences)를 쓰는 틀인지
 * @param ranks 대상군에 신청 순위(rank)를 쓰는 틀인지
 * @param asOf 조건별 기준일(asOf)을 쓰는 틀인지
 * @param referenceDateOptional 공고에 기준일 문구가 없으면 referenceDate를 null로 받는 틀인지 (그러면 판정하는 날 기준)
 */
public record FrameSpec(
    Field field,
    String schema,
    String sourceIdField,
    Set<String> kinds,
    Set<String> statusCodes,
    Set<String> restrictionCodes,
    Set<RegistrationRequirement> registrationRequires,
    boolean preferences,
    boolean ranks,
    boolean asOf,
    boolean referenceDateOptional) {

  public static final FrameSpec HOUSING =
      new FrameSpec(
          Field.HOUSING,
          "housing-judgment.v1",
          "rawPostId",
          Set.of(
              "AGE",
              "RESIDENCE",
              "HOMELESS",
              "INCOME",
              "ASSET",
              "CAR",
              "MARRIAGE",
              "CHILDREN",
              "SAVINGS",
              "STATUS",
              "ANY_OF",
              "ASK"),
          Codes.HOUSING_STATUSES.keySet(),
          Set.of(),
          EnumSet.noneOf(RegistrationRequirement.class),
          false,
          true,
          false,
          false);

  public static final FrameSpec BUSINESS_SPACE =
      new FrameSpec(
          Field.BUSINESS_SPACE,
          "business-space-judgment.v1",
          "rawPostId",
          Set.of(
              "AGE",
              "NATIONALITY",
              "APPLICANT_TYPE",
              "REGION",
              "BUSINESS_REGISTRATION",
              "BUSINESS_CAREER",
              "INDUSTRY",
              "STATUS",
              "EXCLUDED_STATUS",
              "ANY_OF",
              "ASK"),
          Codes.BUSINESS_SPACE_STATUSES.keySet(),
          Codes.BUSINESS_SPACE_RESTRICTIONS.keySet(),
          EnumSet.allOf(RegistrationRequirement.class),
          true,
          true,
          false,
          false);

  public static final FrameSpec STARTUP_SUPPORT =
      new FrameSpec(
          Field.STARTUP_SUPPORT,
          "startup-support-judgment.v1",
          "rawPolicyId",
          Set.of(
              "AGE",
              "REGION",
              "BUSINESS_REGISTRATION",
              "BUSINESS_AGE",
              "CLOSURE",
              "REVENUE",
              "INDUSTRY",
              "STATUS",
              "EXCLUDED_STATUS",
              "ANY_OF",
              "ASK"),
          Codes.STARTUP_SUPPORT_STATUSES.keySet(),
          Codes.STARTUP_SUPPORT_RESTRICTIONS.keySet(),
          EnumSet.of(RegistrationRequirement.REGISTERED, RegistrationRequirement.NOT_REGISTERED),
          true,
          false,
          true,
          true);
}
