package kr.mujuthaek.api.eligibility.controller;

import jakarta.validation.Valid;
import java.util.List;
import java.util.UUID;
import kr.mujuthaek.api.eligibility.controller.spec.NoticeBenefitApiSpec;
import kr.mujuthaek.api.eligibility.dto.request.EvaluateRequest;
import kr.mujuthaek.api.eligibility.dto.response.BenefitSearchResponse;
import kr.mujuthaek.api.eligibility.service.NoticeBenefitService;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
class NoticeBenefitController implements NoticeBenefitApiSpec {

  private final NoticeBenefitService benefits;

  NoticeBenefitController(NoticeBenefitService benefits) {
    this.benefits = benefits;
  }

  @Override
  @PostMapping("/api/v1/eligibility/notices/{id}/benefits")
  public ResponseEntity<List<BenefitSearchResponse.Item>> related(
      @PathVariable UUID id, @Valid @RequestBody EvaluateRequest request) {
    return ResponseEntity.ok()
        .cacheControl(CacheControl.noStore())
        .body(benefits.forNotice(id, request.applicant().toApplicant()));
  }
}
