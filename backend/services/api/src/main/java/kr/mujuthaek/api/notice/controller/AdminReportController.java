package kr.mujuthaek.api.notice.controller;

import jakarta.validation.Valid;
import java.security.Principal;
import java.util.UUID;
import kr.mujuthaek.api.notice.controller.spec.AdminReportApiSpec;
import kr.mujuthaek.api.notice.dto.request.AdminReportResolveRequest;
import kr.mujuthaek.api.notice.dto.response.AdminReportDetailResponse;
import kr.mujuthaek.api.notice.dto.response.AdminReportListResponse;
import kr.mujuthaek.api.notice.dto.response.AdminReportQueueResponse;
import kr.mujuthaek.api.notice.dto.response.AdminReportReviewResponse;
import kr.mujuthaek.api.notice.service.internal.AdminReportQueueService;
import kr.mujuthaek.api.notice.service.internal.NoticeReportService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/** 관리자 제보 화면 API (설명은 {@link AdminReportApiSpec}). */
@RestController
@RequestMapping("/api/admin/reports")
class AdminReportController implements AdminReportApiSpec {

  private final NoticeReportService reports;
  private final AdminReportQueueService queue;

  AdminReportController(NoticeReportService reports, AdminReportQueueService queue) {
    this.reports = reports;
    this.queue = queue;
  }

  @Override
  @GetMapping
  public AdminReportListResponse list(@RequestParam(required = false) String status) {
    return reports.list(status);
  }

  @Override
  @GetMapping("/counts")
  public AdminReportListResponse.Counts counts() {
    return reports.counts();
  }

  @Override
  @GetMapping("/queue")
  public AdminReportQueueResponse queue(
      @RequestParam(defaultValue = "NEW") String status,
      @RequestParam(required = false) String cursor,
      @RequestParam(defaultValue = "20") int size) {
    return queue.queue(status, cursor, size);
  }

  @Override
  @GetMapping("/{id}")
  public AdminReportDetailResponse detail(@PathVariable UUID id) {
    return reports.detail(id);
  }

  @Override
  @PostMapping("/{id}/start")
  public AdminReportDetailResponse start(@PathVariable UUID id, Principal principal) {
    return reports.start(id, admin(principal));
  }

  @Override
  @PostMapping("/{id}/review")
  public AdminReportReviewResponse review(@PathVariable UUID id, Principal principal) {
    return reports.openReview(id, admin(principal));
  }

  @Override
  @PostMapping("/{id}/resolve")
  public AdminReportDetailResponse resolve(
      @PathVariable UUID id,
      @Valid @RequestBody AdminReportResolveRequest request,
      Principal principal) {
    return reports.resolve(id, request, admin(principal));
  }

  private static String admin(Principal principal) {
    return principal == null ? null : principal.getName();
  }
}
