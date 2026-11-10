package kr.mujuthaek.api.eligibility.controller;

import jakarta.validation.Valid;
import java.util.UUID;
import kr.mujuthaek.api.eligibility.controller.spec.SpaceApiSpec;
import kr.mujuthaek.api.eligibility.dto.request.SpaceEvaluateRequest;
import kr.mujuthaek.api.eligibility.dto.request.SpaceSearchRequest;
import kr.mujuthaek.api.eligibility.dto.response.SpaceEvaluationResponse;
import kr.mujuthaek.api.eligibility.dto.response.SpaceSearchResponse;
import kr.mujuthaek.api.eligibility.service.SpaceSearchService;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

/** 사업공간 맞춤 목록·판정 (설명은 {@link SpaceApiSpec}). */
@RestController
class SpaceController implements SpaceApiSpec {

  private final SpaceSearchService spaces;

  SpaceController(SpaceSearchService spaces) {
    this.spaces = spaces;
  }

  @Override
  @PostMapping("/api/v1/spaces/search")
  public ResponseEntity<SpaceSearchResponse> search(
      @Valid @RequestBody SpaceSearchRequest request) {
    return ResponseEntity.ok().cacheControl(CacheControl.noStore()).body(spaces.search(request));
  }

  @Override
  @PostMapping("/api/v1/spaces/{id}/evaluate")
  public ResponseEntity<SpaceEvaluationResponse> evaluate(
      @PathVariable UUID id, @Valid @RequestBody(required = false) SpaceEvaluateRequest request) {
    return ResponseEntity.ok()
        .cacheControl(CacheControl.noStore())
        .body(
            request == null ? spaces.evaluate(id, null) : spaces.evaluate(id, request.applicant()));
  }
}
