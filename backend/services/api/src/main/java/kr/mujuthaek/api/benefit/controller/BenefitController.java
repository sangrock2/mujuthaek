package kr.mujuthaek.api.benefit.controller;

import java.util.UUID;
import kr.mujuthaek.api.benefit.controller.spec.BenefitApiSpec;
import kr.mujuthaek.api.benefit.dto.response.BenefitDetailResponse;
import kr.mujuthaek.api.benefit.service.internal.BenefitDetailService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** 혜택 공개 정보 (설명은 {@link BenefitApiSpec}). 내 조건 판정은 eligibility 모듈에 있어요. */
@RestController
@RequestMapping("/api/v1/benefits")
class BenefitController implements BenefitApiSpec {

  private final BenefitDetailService details;

  BenefitController(BenefitDetailService details) {
    this.details = details;
  }

  @Override
  @GetMapping("/{id}")
  public BenefitDetailResponse detail(@PathVariable UUID id) {
    return details.detail(id);
  }
}
