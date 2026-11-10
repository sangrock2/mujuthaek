package kr.mujuthaek.api.user.service;

import java.util.ArrayList;
import java.util.Collection;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import kr.mujuthaek.api.user.repository.FavoriteRepository;
import kr.mujuthaek.api.user.repository.InterestRepository;
import kr.mujuthaek.api.user.repository.NotificationSettingRepository;
import kr.mujuthaek.api.user.repository.NotificationSettingRepository.Settings;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 알림 대상자 찾기 (notification 모듈이 불러요, contracts/schemas/notification-events.draft.md 5장). 누가 관심 있는지(회원
 * ID)와 회원마다 종류별 켬·끔·조용한 시간을 줘요. 끈 회원도 대상자에 들어가요 (알림함에는 남고 보내지만 않아서).
 */
@Service
public class UserNotificationQueryService {

  private final InterestRepository interests;
  private final FavoriteRepository favorites;
  private final NotificationSettingRepository settings;

  public UserNotificationQueryService(
      InterestRepository interests,
      FavoriteRepository favorites,
      NotificationSettingRepository settings) {
    this.interests = interests;
    this.favorites = favorites;
    this.settings = settings;
  }

  /**
   * 새 공고에 관심 있는 회원: 주거(HOUSING)면 housing_interests, 사업공간(BUSINESS_SPACE)면 business_interests.
   *
   * @param regionCodes 공고 지역 5자리 (NoticePublished.regionCodes, 시도 전체는 xx000)
   * @param noticeType 공고 유형 (주거만 걸러요, 모르면 null)
   */
  @Transactional(readOnly = true)
  public List<UUID> newNoticeAudience(
      String field, List<String> regionCodes, boolean nationwide, String noticeType) {
    String table =
        switch (field) {
          case "HOUSING" -> "housing_interests";
          case "BUSINESS_SPACE" -> "business_interests";
          default -> null;
        };
    return table == null
        ? List.of()
        : interests.audience(table, regionCodes, nationwide, noticeType);
  }

  /**
   * 새 정책에 관심 있는 회원: 지원 정책(BENEFIT)이면 support_interests, 창업지원·사업공간 모집이면 business_interests. 지역을 모르는
   * 정책(UNKNOWN)은 새 소식으로 보내지 않아요 (아무에게나 가지 않게).
   *
   * @param regionScope NATIONWIDE · SIDO · SIGUNGU · UNKNOWN
   * @param regionCodes 시도 2자리 / 시군구 5자리
   */
  @Transactional(readOnly = true)
  public List<UUID> newBenefitAudience(String field, String regionScope, List<String> regionCodes) {
    String table =
        switch (field) {
          case "BENEFIT" -> "support_interests";
          case "STARTUP_SUPPORT", "SPACE_RECRUITMENT" -> "business_interests";
          default -> null;
        };
    if (table == null || "UNKNOWN".equals(regionScope)) {
      return List.of();
    }
    boolean nationwide = "NATIONWIDE".equals(regionScope);
    List<String> codes = new ArrayList<>();
    for (String code : regionCodes == null ? List.<String>of() : regionCodes) {
      codes.add(code.length() == 2 ? code + "000" : code); // 시도 2자리 → 시도 전체 xx000
    }
    return interests.audience(table, codes, nationwide, null);
  }

  /** 이 공고·정책을 관심으로 둔 회원 (targetType NOTICE · BENEFIT · STARTUP_SUPPORT · SPACE_RECRUITMENT) */
  @Transactional(readOnly = true)
  public List<UUID> favoriteAudience(String targetType, UUID targetId) {
    return favorites.userIds(targetType, targetId);
  }

  /** 회원마다 알림 설정. 저장한 적 없는 회원은 기본값이에요 */
  @Transactional(readOnly = true)
  public Map<UUID, NotificationPreference> preferences(Collection<UUID> userIds) {
    Map<UUID, Settings> saved = settings.findAll(userIds);
    Map<UUID, NotificationPreference> out = new HashMap<>();
    for (UUID id : userIds) {
      Settings s = saved.get(id);
      out.put(
          id,
          s == null
              ? NotificationPreference.DEFAULT
              : new NotificationPreference(
                  s.newNotice(),
                  s.newSupport(),
                  s.deadline(),
                  s.correction(),
                  s.followUp(),
                  s.quietEnabled()));
    }
    return out;
  }
}
