package kr.mujuthaek.api.common.region;

import java.time.Duration;
import kr.mujuthaek.api.common.exception.CustomException;
import kr.mujuthaek.api.common.exception.ErrorCode;
import kr.mujuthaek.api.common.region.spec.RegionApiSpec;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.context.request.WebRequest;

/** 공통 코드: 시·도와 시·군·구 (설명은 {@link RegionApiSpec}). 자주 바뀌지 않아서 하루 캐시 + ETag를 붙여요. */
@RestController
@RequestMapping("/api/v1/regions")
class RegionController implements RegionApiSpec {

  private static final CacheControl DAY = CacheControl.maxAge(Duration.ofDays(1)).cachePublic();

  private final RegionQueryService regions;

  RegionController(RegionQueryService regions) {
    this.regions = regions;
  }

  @Override
  @GetMapping
  public ResponseEntity<RegionQueryService.RegionTree> all(WebRequest request) {
    String etag = "\"regions-" + regions.version() + "\"";
    if (request.checkNotModified(etag)) {
      return null; // 304
    }
    return ResponseEntity.ok().cacheControl(DAY).eTag(etag).body(regions.tree());
  }

  @Override
  @GetMapping("/{code}")
  public ResponseEntity<RegionQueryService.Region> one(@PathVariable String code) {
    if (!code.matches("[0-9]{2}([0-9]{3})?")) {
      throw new CustomException(ErrorCode.VALIDATION_FAILED, "regionCode는 2자리(시도) 또는 5자리(시군구)예요");
    }
    var region =
        regions
            .find(code)
            .orElseThrow(() -> new CustomException(ErrorCode.NOT_FOUND, "없는 지역 코드예요"));
    return ResponseEntity.ok().cacheControl(DAY).body(region);
  }
}
