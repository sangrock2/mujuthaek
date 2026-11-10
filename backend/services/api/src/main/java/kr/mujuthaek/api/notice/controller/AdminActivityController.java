package kr.mujuthaek.api.notice.controller;

import kr.mujuthaek.api.notice.controller.spec.AdminActivityApiSpec;
import kr.mujuthaek.api.notice.dto.response.AdminActivityResponse;
import kr.mujuthaek.api.notice.service.internal.AdminActivityService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/** 관리자 「처리 기록」 (설명은 {@link AdminActivityApiSpec}). */
@RestController
@RequestMapping("/api/admin/activity")
class AdminActivityController implements AdminActivityApiSpec {

  private final AdminActivityService activity;

  AdminActivityController(AdminActivityService activity) {
    this.activity = activity;
  }

  @Override
  @GetMapping
  public AdminActivityResponse activity(@RequestParam(defaultValue = "30") int days) {
    return activity.activity(days);
  }
}
