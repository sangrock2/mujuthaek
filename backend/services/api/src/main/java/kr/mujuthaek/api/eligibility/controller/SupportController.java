package kr.mujuthaek.api.eligibility.controller;

import jakarta.validation.Valid;
import java.util.UUID;
import kr.mujuthaek.api.eligibility.controller.spec.SupportApiSpec;
import kr.mujuthaek.api.eligibility.dto.request.SpaceEvaluateRequest;
import kr.mujuthaek.api.eligibility.dto.request.SupportSearchRequest;
import kr.mujuthaek.api.eligibility.dto.response.SupportEvaluationResponse;
import kr.mujuthaek.api.eligibility.dto.response.SupportSearchResponse;
import kr.mujuthaek.api.eligibility.service.SupportSearchService;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

/** 사업 지원 맞춤 목록·판정 (설명은 {@link SupportApiSpec}). */
@RestController
class SupportController implements SupportApiSpec {

  private final SupportSearchService supports;

  SupportController(SupportSearchService supports) {
    this.supports = supports;
  }

  @Override
  @PostMapping("/api/v1/supports/search")
  public ResponseEntity<SupportSearchResponse> search(
      @Valid @RequestBody SupportSearchRequest request) {
    return ResponseEntity.ok().cacheControl(CacheControl.noStore()).body(supports.search(request));
  }

  @Override
  @PostMapping("/api/v1/supports/{id}/evaluate")
  public ResponseEntity<SupportEvaluationResponse> evaluate(
      @PathVariable UUID id, @Valid @RequestBody(required = false) SpaceEvaluateRequest request) {
    return ResponseEntity.ok()
        .cacheControl(CacheControl.noStore())
        .body(
            request == null
                ? supports.evaluate(id, null)
                : supports.evaluate(id, request.applicant()));
  }
}
