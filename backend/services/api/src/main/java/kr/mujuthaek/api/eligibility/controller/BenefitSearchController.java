package kr.mujuthaek.api.eligibility.controller;

import jakarta.validation.Valid;
import java.util.UUID;
import kr.mujuthaek.api.eligibility.controller.spec.BenefitSearchApiSpec;
import kr.mujuthaek.api.eligibility.dto.request.BenefitSearchRequest;
import kr.mujuthaek.api.eligibility.dto.request.EvaluateRequest;
import kr.mujuthaek.api.eligibility.dto.response.BenefitEvaluationResponse;
import kr.mujuthaek.api.eligibility.dto.response.BenefitSearchResponse;
import kr.mujuthaek.api.eligibility.service.BenefitEvaluationService;
import kr.mujuthaek.api.eligibility.service.BenefitSearchService;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

/** 혜택 맞춤 목록·판정 (설명은 {@link BenefitSearchApiSpec}). 판정이 섞여서 eligibility에 있어요. */
@RestController
class BenefitSearchController implements BenefitSearchApiSpec {

  private final BenefitSearchService search;
  private final BenefitEvaluationService evaluations;

  BenefitSearchController(BenefitSearchService search, BenefitEvaluationService evaluations) {
    this.search = search;
    this.evaluations = evaluations;
  }

  @Override
  @PostMapping("/api/v1/benefits/search")
  public ResponseEntity<BenefitSearchResponse> search(
      @Valid @RequestBody BenefitSearchRequest request) {
    return ResponseEntity.ok().cacheControl(CacheControl.noStore()).body(search.search(request));
  }

  @Override
  @PostMapping("/api/v1/benefits/{id}/evaluate")
  public ResponseEntity<BenefitEvaluationResponse> evaluate(
      @PathVariable UUID id, @Valid @RequestBody EvaluateRequest request) {
    return ResponseEntity.ok()
        .cacheControl(CacheControl.noStore())
        .body(evaluations.evaluate(id, request.applicant().toApplicant()));
  }
}
