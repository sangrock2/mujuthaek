package kr.mujuthaek.api.user.service;

import java.time.Clock;
import java.util.UUID;
import kr.mujuthaek.api.user.repository.NotificationSettingRepository;
import kr.mujuthaek.api.user.repository.NotificationSettingRepository.Settings;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 알림 종류별 켬·끔과 조용한 시간 (contracts/schemas/user-preferences.draft.md 2-7). 웹 푸시·이메일이 같이 써요. 끈 종류도
 * 알림함에는 남아요. 웹 푸시 자체의 켬·끔은 기기 구독이에요 (notification 모듈).
 */
@Service
public class NotificationSettingService {

  private final NotificationSettingRepository settings;
  private final Clock clock;

  public NotificationSettingService(NotificationSettingRepository settings, Clock clock) {
    this.settings = settings;
    this.clock = clock;
  }

  /** 저장한 적이 없으면 기본값 (모두 켬, 조용한 시간 끔) */
  @Transactional(readOnly = true)
  public Settings get(UUID userId) {
    return settings.find(userId).orElse(Settings.DEFAULT);
  }

  @Transactional
  public Settings save(UUID userId, Settings s) {
    settings.save(userId, s, clock.instant());
    return s;
  }
}
