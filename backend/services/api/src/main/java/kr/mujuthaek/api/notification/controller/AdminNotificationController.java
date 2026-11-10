package kr.mujuthaek.api.notification.controller;

import kr.mujuthaek.api.notification.controller.spec.AdminNotificationApiSpec;
import kr.mujuthaek.api.notification.dto.response.AdminNotificationStatsResponse;
import kr.mujuthaek.api.notification.service.internal.NotificationStatsService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/** 관리자 「알림」 화면 (설명은 {@link AdminNotificationApiSpec}). */
@RestController
class AdminNotificationController implements AdminNotificationApiSpec {

  private final NotificationStatsService stats;

  AdminNotificationController(NotificationStatsService stats) {
    this.stats = stats;
  }

  @Override
  @GetMapping("/api/admin/notifications/stats")
  public AdminNotificationStatsResponse stats(@RequestParam(defaultValue = "7") int days) {
    return stats.stats(days);
  }
}
