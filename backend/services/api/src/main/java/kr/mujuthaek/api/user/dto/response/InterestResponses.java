package kr.mujuthaek.api.user.dto.response;

import java.util.List;

/**
 * 관심 조건 (GET·PUT /api/users/me/interests/{housing|business|support}). saved가 false면 저장 전이라 새 소식 알림을
 * 받지 않아요.
 */
public final class InterestResponses {

  private InterestResponses() {}

  public record Housing(
      boolean saved,
      List<String> regionCodes,
      boolean includeNationwide,
      List<String> noticeTypes) {}

  public record Business(
      boolean saved,
      List<String> regionCodes,
      boolean includeNationwide,
      List<String> industryCodes,
      List<String> startupStages) {}

  public record Support(
      boolean saved,
      List<String> regionCodes,
      boolean includeNationwide,
      List<String> supportKinds) {}
}
