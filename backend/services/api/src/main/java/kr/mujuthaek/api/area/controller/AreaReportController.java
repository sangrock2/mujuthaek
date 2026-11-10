package kr.mujuthaek.api.area.controller;

import jakarta.validation.Valid;
import java.security.Principal;
import java.util.UUID;
import kr.mujuthaek.api.area.controller.spec.AreaReportApiSpec;
import kr.mujuthaek.api.area.dto.request.AreaReportRequest;
import kr.mujuthaek.api.area.dto.request.AreaReportResolveRequest;
import kr.mujuthaek.api.area.dto.response.AreaReportResponse;
import kr.mujuthaek.api.area.service.AreaReportService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/** 생활권 제보 (설명은 {@link AreaReportApiSpec}). 회원·관리자는 로그인 계정 ID(Principal 이름)로만 남겨요. */
@RestController
class AreaReportController implements AreaReportApiSpec {

  private final AreaReportService reports;

  AreaReportController(AreaReportService reports) {
    this.reports = reports;
  }

  @Override
  @PostMapping("/api/v1/notices/{id}/area-reports")
  public AreaReportResponse.Created report(
      @PathVariable UUID id, @Valid @RequestBody AreaReportRequest request, Principal principal) {
    return reports.report(id, request, name(principal));
  }

  @Override
  @GetMapping("/api/admin/area-reports")
  public AreaReportResponse.ListView list(@RequestParam(required = false) String status) {
    return reports.list(status);
  }

  @Override
  @GetMapping("/api/admin/area-reports/counts")
  public AreaReportResponse.Counts counts() {
    return reports.counts();
  }

  @Override
  @GetMapping("/api/admin/area-reports/{id}")
  public AreaReportResponse.Detail detail(@PathVariable UUID id) {
    return reports.detail(id);
  }

  @Override
  @PostMapping("/api/admin/area-reports/{id}/start")
  public AreaReportResponse.Detail start(@PathVariable UUID id, Principal principal) {
    return reports.start(id, name(principal));
  }

  @Override
  @PostMapping("/api/admin/area-reports/{id}/resolve")
  public AreaReportResponse.Detail resolve(
      @PathVariable UUID id,
      @Valid @RequestBody AreaReportResolveRequest request,
      Principal principal) {
    return reports.resolve(id, request, name(principal));
  }

  private static String name(Principal principal) {
    return principal == null ? null : principal.getName();
  }
}
