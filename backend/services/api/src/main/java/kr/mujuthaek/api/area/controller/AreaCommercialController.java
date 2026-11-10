package kr.mujuthaek.api.area.controller;

import java.util.UUID;
import kr.mujuthaek.api.area.controller.spec.AreaCommercialApiSpec;
import kr.mujuthaek.api.area.domain.CommercialScore;
import kr.mujuthaek.api.area.service.AreaCommercialService;
import kr.mujuthaek.api.common.exception.CustomException;
import kr.mujuthaek.api.common.exception.ErrorCode;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * 공공 상가 위치의 상권 점수 (설명은 {@link AreaCommercialApiSpec}). API 문서의 GET
 * /areas/commercial/{siteId}?industry=예요.
 */
@RestController
@RequestMapping("/api/v1/areas/commercial")
class AreaCommercialController implements AreaCommercialApiSpec {

  private final AreaCommercialService commercial;

  AreaCommercialController(AreaCommercialService commercial) {
    this.commercial = commercial;
  }

  @Override
  @GetMapping("/{siteId}")
  public CommercialScore score(
      @PathVariable UUID siteId, @RequestParam(required = false) String industry) {
    return commercial
        .score(siteId, industry)
        .orElseThrow(() -> new CustomException(ErrorCode.AREA_SITE_NOT_FOUND));
  }
}
