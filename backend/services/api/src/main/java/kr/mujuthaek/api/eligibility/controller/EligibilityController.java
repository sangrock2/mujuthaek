package kr.mujuthaek.api.eligibility.controller;

import jakarta.validation.Valid;
import java.time.Duration;
import java.util.UUID;
import kr.mujuthaek.api.eligibility.controller.spec.EligibilityApiSpec;
import kr.mujuthaek.api.eligibility.dto.request.EvaluateRequest;
import kr.mujuthaek.api.eligibility.dto.request.PrepareCostRequest;
import kr.mujuthaek.api.eligibility.dto.request.SubscriptionScoreRequest;
import kr.mujuthaek.api.eligibility.dto.response.CriteriaResponse;
import kr.mujuthaek.api.eligibility.dto.response.NoticeEvaluationResponse;
import kr.mujuthaek.api.eligibility.rule.PrepareCost;
import kr.mujuthaek.api.eligibility.rule.SubscriptionScore;
import kr.mujuthaek.api.eligibility.service.CriteriaService;
import kr.mujuthaek.api.eligibility.service.NoticeEvaluationService;
import kr.mujuthaek.api.eligibility.service.PrepareCostService;
import kr.mujuthaek.api.eligibility.service.SubscriptionScoreService;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/** 판정 API (설명은 {@link EligibilityApiSpec}). 판정 API는 /eligibility 아래에 모아요 (판정 경로 B). */
@RestController
@RequestMapping("/api/v1/eligibility")
class EligibilityController implements EligibilityApiSpec {

  /** 판정 응답은 사용자 조건으로 계산한 값이라 어디에도 캐시하지 않아요. */
  static final CacheControl NO_STORE = CacheControl.noStore();

  private final CriteriaService criteria;
  private final SubscriptionScoreService scores;
  private final NoticeEvaluationService evaluations;
  private final PrepareCostService prepareCost;

  EligibilityController(
      CriteriaService criteria,
      SubscriptionScoreService scores,
      NoticeEvaluationService evaluations,
      PrepareCostService prepareCost) {
    this.criteria = criteria;
    this.scores = scores;
    this.evaluations = evaluations;
    this.prepareCost = prepareCost;
  }

  @Override
  @PostMapping("/prepare-cost")
  public ResponseEntity<PrepareCost.Result> prepareCost(
      @Valid @RequestBody PrepareCostRequest request) {
    return ResponseEntity.ok()
        .cacheControl(NO_STORE)
        .body(prepareCost.prepare(request.depositWon(), request.applicant().toApplicant()));
  }

  @Override
  @PostMapping("/notices/{id}/evaluate")
  public ResponseEntity<NoticeEvaluationResponse> evaluateNotice(
      @PathVariable UUID id, @Valid @RequestBody EvaluateRequest request) {
    return ResponseEntity.ok()
        .cacheControl(NO_STORE)
        .body(evaluations.evaluate(id, request.applicant().toApplicant()));
  }

  @Override
  @PostMapping("/subscription-score")
  public ResponseEntity<SubscriptionScore.Score> subscriptionScore(
      @Valid @RequestBody SubscriptionScoreRequest request) {
    return ResponseEntity.ok()
        .cacheControl(NO_STORE)
        .body(scores.score(request.applicant().toInput(), request.referenceDate()));
  }

  @Override
  @GetMapping("/criteria")
  public ResponseEntity<CriteriaResponse> criteria(
      @RequestParam(required = false) Integer year,
      @RequestParam(required = false) String noticeType) {
    return ResponseEntity.ok()
        .cacheControl(CacheControl.maxAge(Duration.ofDays(1)).cachePublic())
        .body(criteria.criteria(year, noticeType));
  }
}
