package kr.mujuthaek.api.notice.controller;

import jakarta.validation.Valid;
import java.security.Principal;
import java.util.UUID;
import kr.mujuthaek.api.notice.controller.spec.AdminPolicyDuplicateApiSpec;
import kr.mujuthaek.api.notice.dto.request.AdminPolicyDuplicateDecideRequest;
import kr.mujuthaek.api.notice.dto.response.AdminPolicyDuplicateResponse;
import kr.mujuthaek.api.notice.service.internal.PolicyDuplicateService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/** 관리자 「제보·신고」의 「중복 의심」 (설명은 {@link AdminPolicyDuplicateApiSpec}). */
@RestController
@RequestMapping("/api/admin/policy-duplicates")
class AdminPolicyDuplicateController implements AdminPolicyDuplicateApiSpec {

  private final PolicyDuplicateService duplicates;

  AdminPolicyDuplicateController(PolicyDuplicateService duplicates) {
    this.duplicates = duplicates;
  }

  @Override
  @GetMapping
  public AdminPolicyDuplicateResponse list(@RequestParam(required = false) String status) {
    return duplicates.list(status);
  }

  @Override
  @GetMapping("/counts")
  public AdminPolicyDuplicateResponse.Counts counts() {
    return duplicates.counts();
  }

  @Override
  @PostMapping("/{later}/{earlier}/decide")
  public AdminPolicyDuplicateResponse.Counts decide(
      @PathVariable UUID later,
      @PathVariable UUID earlier,
      @Valid @RequestBody AdminPolicyDuplicateDecideRequest request,
      Principal principal) {
    duplicates.decide(
        later, earlier, request.action(), principal == null ? null : principal.getName());
    return duplicates.counts();
  }
}
