package kr.mujuthaek.api.eligibility.controller;

import jakarta.validation.Valid;
import java.security.Principal;
import java.time.LocalDate;
import java.util.List;
import java.util.UUID;
import kr.mujuthaek.api.eligibility.controller.spec.AdminCriteriaApiSpec;
import kr.mujuthaek.api.eligibility.dto.request.AdminCriteriaRequest;
import kr.mujuthaek.api.eligibility.dto.request.RegulatedAreaRequest;
import kr.mujuthaek.api.eligibility.dto.response.AdminCriteriaResponse;
import kr.mujuthaek.api.eligibility.dto.response.CriteriaUsageResponse;
import kr.mujuthaek.api.eligibility.dto.response.RegulatedAreaResponse;
import kr.mujuthaek.api.eligibility.service.AdminCriteriaService;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/** 관리자 기준값 화면 (설명은 {@link AdminCriteriaApiSpec}). 고친 관리자는 로그인 계정 ID(Principal 이름)로 남겨요. */
@RestController
@RequestMapping("/api/admin")
class AdminCriteriaController implements AdminCriteriaApiSpec {

  private final AdminCriteriaService criteria;

  AdminCriteriaController(AdminCriteriaService criteria) {
    this.criteria = criteria;
  }

  @Override
  @GetMapping("/criteria/{kind}")
  public AdminCriteriaResponse criteria(@PathVariable String kind) {
    return criteria.criteria(kind);
  }

  @Override
  @PutMapping("/criteria/{kind}/{year}")
  public AdminCriteriaResponse save(
      @PathVariable String kind,
      @PathVariable int year,
      @Valid @RequestBody AdminCriteriaRequest request,
      Principal principal) {
    return criteria.save(kind, year, request, admin(principal));
  }

  @Override
  @GetMapping("/criteria/{kind}/history")
  public AdminCriteriaResponse.Changes history(@PathVariable String kind) {
    return criteria.history(kind);
  }

  @Override
  @GetMapping("/criteria/{kind}/usage")
  public CriteriaUsageResponse usage(@PathVariable String kind) {
    return criteria.usage(kind);
  }

  @Override
  @GetMapping("/regulated-areas")
  public List<RegulatedAreaResponse> regulatedAreas(
      @RequestParam(defaultValue = "false") boolean active) {
    return criteria.regulatedAreas(active);
  }

  @Override
  @PostMapping("/regulated-areas")
  public RegulatedAreaResponse add(
      @Valid @RequestBody RegulatedAreaRequest request, Principal principal) {
    return criteria.addRegulatedArea(request, admin(principal));
  }

  @Override
  @PostMapping("/regulated-areas/{id}/end")
  public RegulatedAreaResponse end(
      @PathVariable UUID id,
      @RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
          LocalDate until,
      Principal principal) {
    return criteria.endRegulatedArea(id, until, admin(principal));
  }

  private static String admin(Principal principal) {
    return principal == null ? null : principal.getName();
  }
}
