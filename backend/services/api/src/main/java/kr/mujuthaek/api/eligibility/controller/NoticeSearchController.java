package kr.mujuthaek.api.eligibility.controller;

import jakarta.validation.Valid;
import kr.mujuthaek.api.eligibility.controller.spec.NoticeSearchApiSpec;
import kr.mujuthaek.api.eligibility.dto.request.NoticeSearchRequest;
import kr.mujuthaek.api.eligibility.dto.response.NoticeSearchResponse;
import kr.mujuthaek.api.eligibility.service.NoticeSearchService;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

/**
 * 공고 맞춤 목록 (설명은 {@link NoticeSearchApiSpec}). 판정이 섞인 목록이라 eligibility에 있어요 (notice는 eligibility를 부를
 * 수 없어서).
 */
@RestController
class NoticeSearchController implements NoticeSearchApiSpec {

  private final NoticeSearchService search;

  NoticeSearchController(NoticeSearchService search) {
    this.search = search;
  }

  @Override
  @PostMapping("/api/v1/notices/search")
  public ResponseEntity<NoticeSearchResponse> search(
      @Valid @RequestBody NoticeSearchRequest request) {
    return ResponseEntity.ok().cacheControl(CacheControl.noStore()).body(search.search(request));
  }
}
