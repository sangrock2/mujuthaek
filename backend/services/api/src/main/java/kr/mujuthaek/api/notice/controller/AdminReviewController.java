package kr.mujuthaek.api.notice.controller;

import jakarta.validation.Valid;
import java.security.Principal;
import java.util.List;
import java.util.UUID;
import kr.mujuthaek.api.notice.controller.spec.AdminReviewApiSpec;
import kr.mujuthaek.api.notice.dto.request.AdminReviewDecisionRequest;
import kr.mujuthaek.api.notice.dto.response.AdminReviewCountsResponse;
import kr.mujuthaek.api.notice.dto.response.AdminReviewDecisionResponse;
import kr.mujuthaek.api.notice.dto.response.AdminReviewDetailResponse;
import kr.mujuthaek.api.notice.dto.response.AdminReviewListResponse;
import kr.mujuthaek.api.notice.dto.response.AdminReviewQueueResponse;
import kr.mujuthaek.api.notice.dto.response.AdminReviewStatsResponse;
import kr.mujuthaek.api.notice.service.internal.AdminReviewService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/** 관리자 공고 검수 (설명은 {@link AdminReviewApiSpec}). 검수자는 사용자 모듈 타입에 기대지 않으려고 표준 Principal로 받아요. */
@RestController
@RequestMapping("/api/admin/reviews")
class AdminReviewController implements AdminReviewApiSpec {

  private final AdminReviewService reviews;

  AdminReviewController(AdminReviewService reviews) {
    this.reviews = reviews;
  }

  @Override
  @GetMapping("/queue")
  public AdminReviewQueueResponse queue(
      @RequestParam(required = false) String kinds,
      @RequestParam(required = false) String reason,
      @RequestParam(required = false) String cursor,
      @RequestParam(defaultValue = "50") int size) {
    return reviews.queue(kinds, reason, cursor, size);
  }

  @Override
  @GetMapping("/counts")
  public AdminReviewCountsResponse counts() {
    return reviews.counts();
  }

  @Override
  @GetMapping("/stats")
  public AdminReviewStatsResponse stats(@RequestParam(defaultValue = "7") int days) {
    return reviews.stats(days);
  }

  @Override
  @GetMapping("/urgent")
  public List<AdminReviewListResponse.Item> urgent(@RequestParam(defaultValue = "3") int days) {
    return reviews.urgent(days);
  }

  @Override
  @GetMapping("/{id}")
  public AdminReviewDetailResponse detail(@PathVariable UUID id) {
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
