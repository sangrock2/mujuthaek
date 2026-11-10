package kr.mujuthaek.api.area.controller;

import jakarta.validation.Valid;
import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import kr.mujuthaek.api.area.controller.spec.AreaApiSpec;
import kr.mujuthaek.api.area.domain.AreaCriteria;
import kr.mujuthaek.api.area.domain.SiteDetail;
import kr.mujuthaek.api.area.domain.SiteScore;
import kr.mujuthaek.api.area.dto.request.AreaScoreRequest;
import kr.mujuthaek.api.area.dto.response.AreaScoreResponse;
import kr.mujuthaek.api.area.service.AreaScoreService;
import kr.mujuthaek.api.area.service.AreaSiteService;
import kr.mujuthaek.api.common.exception.CustomException;
import kr.mujuthaek.api.common.exception.ErrorCode;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * area 조회 (설명은 {@link AreaApiSpec}). API 문서 area 모듈이에요. 총점·통근은 사용자 가중치·직장 위치가 들어가서 GET이 아니라 POST로
 * 받고 no-store로 돌려줘요(판정 API와 같아요).
 */
@RestController
@RequestMapping("/api/v1/areas")
class AreaController implements AreaApiSpec {

  private static final CacheControl NO_STORE = CacheControl.noStore();

  private final AreaSiteService sites;
  private final AreaScoreService scores;

  AreaController(AreaSiteService sites, AreaScoreService scores) {
    this.sites = sites;
    this.scores = scores;
  }

  @Override
  @GetMapping("/sites/{siteId}")
  public SiteDetail site(@PathVariable UUID siteId) {
    return sites.site(siteId).orElseThrow(() -> new CustomException(ErrorCode.AREA_SITE_NOT_FOUND));
  }

  @Override
  @PostMapping("/score")
  public ResponseEntity<AreaScoreResponse> score(@Valid @RequestBody AreaScoreRequest request) {
    List<SiteScore> items =
        scores.score(
            request.siteIds(),
            request.priorities() == null ? Map.of() : request.priorities().toMap(),
            request.workplace() == null ? null : request.workplace().toCoordinate());
    return ResponseEntity.ok().cacheControl(NO_STORE).body(new AreaScoreResponse(items));
  }

  @Override
  @GetMapping("/criteria")
  public ResponseEntity<AreaCriteria> criteria() {
    return ResponseEntity.ok()
        .cacheControl(CacheControl.maxAge(Duration.ofDays(1)).cachePublic())
        .body(sites.criteria());
  }
}
