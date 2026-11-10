package kr.mujuthaek.api.notice.controller;

import jakarta.validation.Valid;
import java.security.Principal;
import java.util.UUID;
import kr.mujuthaek.api.notice.controller.spec.NoticeReportApiSpec;
import kr.mujuthaek.api.notice.dto.request.GeneralReportRequest;
import kr.mujuthaek.api.notice.dto.request.NoticeReportRequest;
import kr.mujuthaek.api.notice.dto.response.NoticeReportCreatedResponse;
import kr.mujuthaek.api.notice.service.internal.NoticeReportService;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

/**
 * 제보 받기 (설명은 {@link NoticeReportApiSpec}).
 *
 * <p>제보한 회원은 로그인 계정 ID(Principal 이름)로만 남겨요. 사용자 모듈 타입에 기대지 않아요.
 */
@RestController
class NoticeReportController implements NoticeReportApiSpec {

  private final NoticeReportService reports;

  NoticeReportController(NoticeReportService reports) {
    this.reports = reports;
  }

  @Override
  @PostMapping("/api/v1/programs/{id}/reports")
  public NoticeReportCreatedResponse reportProgram(
      @PathVariable UUID id, @Valid @RequestBody NoticeReportRequest request, Principal principal) {
    return reports.reportProgram(id, request, principal == null ? null : principal.getName());
  }

  @Override
  @PostMapping("/api/v1/benefits/{id}/reports")
  public NoticeReportCreatedResponse reportBenefit(
      @PathVariable UUID id, @Valid @RequestBody NoticeReportRequest request, Principal principal) {
    return reports.reportBenefit(id, request, principal == null ? null : principal.getName());
  }

  @Override
  @PostMapping("/api/v1/reports")
  public NoticeReportCreatedResponse reportGeneral(
      @Valid @RequestBody GeneralReportRequest request, Principal principal) {
    return reports.reportGeneral(request, principal == null ? null : principal.getName());
  }

  @Override
  @PostMapping("/api/v1/notices/{id}/reports")
  public NoticeReportCreatedResponse report(
      @PathVariable UUID id, @Valid @RequestBody NoticeReportRequest request, Principal principal) {
    return reports.report(id, request, principal == null ? null : principal.getName());
  }
}
