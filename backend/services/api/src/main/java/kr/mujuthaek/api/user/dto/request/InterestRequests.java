package kr.mujuthaek.api.user.dto.request;

import java.util.List;

/** 관심 조건 저장 본문 (PUT /api/users/me/interests/{housing|business|support}). 목록은 비워도 돼요. */
public final class InterestRequests {

  private InterestRequests() {}

  /**
   * @param regionCodes 살고 싶은 곳 (시군구 5자리, 시도 전체 xx000), 30개까지
   * @param includeNationwide 전국 대상 공고도 받기 (없으면 true)
   * @param noticeTypes 공고 유형 (빈 목록 = 전부)
   */
  public record Housing(
      List<String> regionCodes, Boolean includeNationwide, List<String> noticeTypes) {}

  /**
   * @param industryCodes 표준산업분류 대분류 A~U (빈 목록 = 전부)
   * @param startupStages PRE_STARTUP · OPERATING (빈 목록 = 전부)
   */
  public record Business(
      List<String> regionCodes,
      Boolean includeNationwide,
      List<String> industryCodes,
      List<String> startupStages) {}

  /**
   * @param regionCodes 혜택 관심 지역 (보통 사는 곳)
   * @param supportKinds RENT · DEPOSIT_LOAN · PURCHASE_LOAN · HOUSING_SUPPLY · MOVE_IN_GRANT · CASH
   *     (빈 목록 = 전부)
   */
  public record Support(
      List<String> regionCodes, Boolean includeNationwide, List<String> supportKinds) {}
}
