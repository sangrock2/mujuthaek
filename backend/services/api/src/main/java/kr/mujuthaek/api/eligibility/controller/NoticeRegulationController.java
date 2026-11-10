package kr.mujuthaek.api.eligibility.controller;

import java.util.UUID;
import kr.mujuthaek.api.eligibility.controller.spec.NoticeRegulationApiSpec;
import kr.mujuthaek.api.eligibility.dto.response.NoticeRegulationResponse;
import kr.mujuthaek.api.eligibility.service.NoticeRegulationService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** 공고 지역의 규제지역 안내 (설명은 {@link NoticeRegulationApiSpec}). */
@RestController
@RequestMapping("/api/v1/eligibility/notices")
class NoticeRegulationController implements NoticeRegulationApiSpec {

  private final NoticeRegulationService regulation;

  NoticeRegulationController(NoticeRegulationService regulation) {
    this.regulation = regulation;
  }

  @Override
  @GetMapping("/{id}/regulation")
  public NoticeRegulationResponse regulation(@PathVariable UUID id) {
    return regulation.forNotice(id);
  }
}
