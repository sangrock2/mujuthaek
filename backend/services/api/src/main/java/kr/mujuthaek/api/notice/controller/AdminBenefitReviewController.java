package kr.mujuthaek.api.notice.controller;

import jakarta.validation.Valid;
import java.security.Principal;
import java.util.UUID;
import kr.mujuthaek.api.notice.controller.spec.AdminBenefitReviewApiSpec;
import kr.mujuthaek.api.notice.dto.request.AdminReviewDecisionRequest;
import kr.mujuthaek.api.notice.dto.response.AdminBenefitReviewCountsResponse;
import kr.mujuthaek.api.notice.dto.response.AdminBenefitReviewDetailResponse;
import kr.mujuthaek.api.notice.dto.response.AdminReviewDecisionResponse;
import kr.mujuthaek.api.notice.service.internal.AdminBenefitReviewService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** 관리자 혜택(주거·이주 정책) 검수 (설명은 {@link AdminBenefitReviewApiSpec}). */
@RestController
@RequestMapping("/api/admin/benefit-reviews")
class AdminBenefitReviewController implements AdminBenefitReviewApiSpec {

  private final AdminBenefitReviewService reviews;

  AdminBenefitReviewController(AdminBenefitReviewService reviews) {
    this.reviews = reviews;
  }

  @Override
  @GetMapping("/counts")
  public AdminBenefitReviewCountsResponse counts() {
    return reviews.counts();
  }

  @Override
  @GetMapping("/{id}")
  public AdminBenefitReviewDetailResponse detail(@PathVariable UUID id) {
    return reviews.detail(id.toString());
  }

  @Override
  @PostMapping("/{id}/approve")
  public AdminReviewDecisionResponse approve(
      @PathVariable UUID id,
      @Valid @RequestBody(required = false) AdminReviewDecisionRequest request,
      Principal principal) {
    return reviews.approve(id.toString(), request, reviewer(principal));
  }

  @Override
  @PostMapping("/{id}/reject")
  public AdminReviewDecisionResponse reject(
      @PathVariable UUID id,
      @Valid @RequestBody(required = false) AdminReviewDecisionRequest request,
      Principal principal) {
    return reviews.reject(id.toString(), request, reviewer(principal));
  }

  private static String reviewer(Principal principal) {
    return principal == null ? null : principal.getName();
  }
}
