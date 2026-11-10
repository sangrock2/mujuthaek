package kr.mujuthaek.api.notice.controller;

import java.time.LocalDate;
import java.util.List;
import java.util.UUID;
import kr.mujuthaek.api.common.dto.response.CursorPageResponse;
import kr.mujuthaek.api.notice.controller.spec.NoticeApiSpec;
import kr.mujuthaek.api.notice.dto.request.NoticeListFilter;
import kr.mujuthaek.api.notice.dto.response.NoticeDetailResponse;
import kr.mujuthaek.api.notice.dto.response.NoticeMapResponse;
import kr.mujuthaek.api.notice.dto.response.NoticeSummaryResponse;
import kr.mujuthaek.api.notice.dto.response.NoticeUnitResponse;
import kr.mujuthaek.api.notice.dto.response.NoticeVersionResponse;
import kr.mujuthaek.api.notice.service.NoticeQueryService;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/** 누구나 보는 공고 API (설명은 {@link NoticeApiSpec}). */
@RestController
@RequestMapping("/api/v1/notices")
class NoticeController implements NoticeApiSpec {

  private final NoticeQueryService notices;

  NoticeController(NoticeQueryService notices) {
    this.notices = notices;
  }

  @Override
  @GetMapping
  public CursorPageResponse<NoticeSummaryResponse> list(
      @RequestParam(required = false) String field,
      @RequestParam(required = false) List<String> regionCodes,
      @RequestParam(required = false) String tenure,
      @RequestParam(required = false) List<String> noticeTypes,
      @RequestParam(required = false) List<String> providers,
      @RequestParam(required = false) List<String> statuses,
      @RequestParam(required = false) String sort,
      @RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
          LocalDate applyEndFrom,
      @RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
          LocalDate applyEndTo,
      @RequestParam(required = false) String cursor,
      @RequestParam(required = false) Integer size) {
    var filter =
        new NoticeListFilter(
            field,
            regionCodes,
            tenure,
            noticeTypes,
            providers,
            statuses,
            sort,
            applyEndFrom,
            applyEndTo);
    return notices.list(filter, cursor, size);
  }

  @Override
  @GetMapping("/map")
  public NoticeMapResponse map(
      @RequestParam double swLat,
      @RequestParam double swLng,
      @RequestParam double neLat,
      @RequestParam double neLng,
      @RequestParam(required = false) Integer zoom,
      @RequestParam(required = false) String tenure,
      @RequestParam(required = false) List<String> noticeTypes,
      @RequestParam(required = false) List<String> providers,
      @RequestParam(required = false) List<String> statuses) {
    return notices.map(swLat, swLng, neLat, neLng, zoom, tenure, noticeTypes, providers, statuses);
  }

  @Override
  @GetMapping("/{id}")
  public NoticeDetailResponse detail(@PathVariable UUID id) {
    return notices.detail(id);
  }

  @Override
  @GetMapping("/{id}/units")
  public CursorPageResponse<NoticeUnitResponse> units(
      @PathVariable UUID id,
      @RequestParam(required = false) String siteId,
      @RequestParam(required = false) String cursor,
      @RequestParam(required = false) Integer size) {
    return notices.units(id, siteId, cursor, size);
  }

  @Override
  @GetMapping("/{id}/versions")
  public List<NoticeVersionResponse> versions(@PathVariable UUID id) {
    return notices.versions(id);
  }
}
