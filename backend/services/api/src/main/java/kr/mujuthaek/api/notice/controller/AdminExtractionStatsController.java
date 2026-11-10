package kr.mujuthaek.api.notice.controller;

import kr.mujuthaek.api.notice.controller.spec.AdminExtractionStatsApiSpec;
import kr.mujuthaek.api.notice.service.internal.AdminExtractionStatsService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import tools.jackson.databind.JsonNode;

/**
 * 관리자 「추출 비용·품질」 (설명은 {@link AdminExtractionStatsApiSpec}). 공고 검수 경로 아래에 두어 「추출 과정 보기」처럼 공고 검수 권한으로
 * 열려요(SecurityConfig의 /api/admin/reviews/**).
 */
@RestController
@RequestMapping("/api/admin/reviews/extraction-stats")
class AdminExtractionStatsController implements AdminExtractionStatsApiSpec {

  private final AdminExtractionStatsService stats;

  AdminExtractionStatsController(AdminExtractionStatsService stats) {
    this.stats = stats;
  }

  @Override
  @GetMapping
  public JsonNode stats(@RequestParam(defaultValue = "30") int days) {
    return stats.stats(days);
  }
}
