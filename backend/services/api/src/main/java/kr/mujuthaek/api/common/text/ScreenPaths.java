package kr.mujuthaek.api.common.text;

import java.util.UUID;

/**
 * 프론트(PWA) 화면 주소. 알림을 누르거나 관심 공고·내 제보를 누르면 갈 곳이라 여러 모듈이 같은 규칙을 써요.
 *
 * <ul>
 *   <li>공고: 사업공간 공고는 사업공간 상세(/business/spaces/{id}), 주거 공고는 공고 상세(/notices/{id})
 *   <li>창업지원 사업은 사업 지원 상세(/business/support/{id}), 사업공간 모집은 사업공간 상세(/business/spaces/{id}) — 맞춤
 *       목록(/supports, /spaces)과 같은 정책 ID
 *   <li>그 밖의 지원 정책(혜택)은 /benefits/{id}
 * </ul>
 */
public final class ScreenPaths {

  /** 일반 제보처럼 대상이 없을 때: 내 정보의 제보 탭 */
  public static final String MY_REPORTS = "/me?tab=reports";

  private ScreenPaths() {}

  /** 대상 종류(NOTICE · BENEFIT · STARTUP_SUPPORT · SPACE_RECRUITMENT)와 ID로 */
  public static String of(String targetType, UUID id) {
    return switch (targetType) {
          case "NOTICE" -> "/notices/";
          case "STARTUP_SUPPORT" -> "/business/support/";
          case "SPACE_RECRUITMENT" -> "/business/spaces/";
          default -> "/benefits/";
        }
        + id;
  }

  /** 공고 화면 (공고 분야가 BUSINESS_SPACE면 사업공간 상세) */
  public static String notice(UUID noticeId, String field) {
    return ("BUSINESS_SPACE".equals(field) ? "/business/spaces/" : "/notices/") + noticeId;
  }
}
