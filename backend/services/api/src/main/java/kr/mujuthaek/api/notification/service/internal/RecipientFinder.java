package kr.mujuthaek.api.notification.service.internal;

import java.util.List;
import java.util.UUID;

/**
 * 알림 받을 회원 찾기 (contracts/schemas/notification-events.draft.md 5장). 관심 조건·관심 공고로 고르고, 회원마다 이 종류를
 * 켰는지(푸시·이메일로 보낼지)와 조용한 시간을 붙여요. 끈 회원도 돌려줘요 (알림함에는 남아서).
 */
public interface RecipientFinder {

  /** 새 지원 정책·창업지원·사업공간 모집(NEW_SUPPORT)에 관심 있는 회원 */
  List<Recipient> forNewBenefit(String field, String regionScope, List<String> regionCodes);

  /**
   * 새 주거·사업공간 공고(NEW_NOTICE)에 관심 있는 회원 (주거면 housing_interests, 사업공간이면 business_interests)
   *
   * @param regionCodes 공고가 걸친 지역 5자리 (NoticePublished.regionCodes)
   * @param noticeType 공고 유형 (주거 관심 조건의 유형으로 걸러요, 모르면 null)
   */
  List<Recipient> forNewNotice(
      String field, List<String> regionCodes, boolean nationwide, String noticeType);

  /**
   * 이 공고·지원 정책·사업공간 모집을 관심 공고로 둔 회원
   *
   * @param targetType NOTICE · BENEFIT · STARTUP_SUPPORT · SPACE_RECRUITMENT
   * @param type 보낼 알림 종류 (회원이 이 종류를 켰는지 볼 때 써요)
   */
  List<Recipient> forFavorite(String targetType, UUID targetId, String type);

  /** 제보한 회원 한 명 (REPORT_ANSWERED). 본인 제보의 답장이라 테스트 회원은 덧붙이지 않아요 */
  Recipient forReporter(UUID userId);
}
