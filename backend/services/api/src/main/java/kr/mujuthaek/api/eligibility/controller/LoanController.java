package kr.mujuthaek.api.eligibility.controller;

import kr.mujuthaek.api.eligibility.controller.spec.LoanApiSpec;
import kr.mujuthaek.api.eligibility.dto.request.LoanEvaluateRequest;
import kr.mujuthaek.api.eligibility.model.LoanResult;
import kr.mujuthaek.api.eligibility.service.LoanQueryService;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** 대출 자격 판정 (설명은 {@link LoanApiSpec}). */
@RestController
@RequestMapping("/api/v1/eligibility")
class LoanController implements LoanApiSpec {

  private final LoanQueryService loans;

  LoanController(LoanQueryService loans) {
    this.loans = loans;
  }

  @Override
  @PostMapping("/loans/evaluate")
  public ResponseEntity<LoanResult> evaluate(@RequestBody LoanEvaluateRequest request) {
    return ResponseEntity.ok()
        .cacheControl(CacheControl.noStore())
        .body(loans.judge(request.profile(), request.asOf()));
  }
}
