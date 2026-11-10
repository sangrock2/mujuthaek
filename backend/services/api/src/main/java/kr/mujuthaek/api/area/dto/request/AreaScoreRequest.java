package kr.mujuthaek.api.area.dto.request;

import jakarta.validation.Valid;
import jakarta.validation.constraints.DecimalMax;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.util.EnumMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import kr.mujuthaek.api.area.domain.Coordinate;
import kr.mujuthaek.api.area.domain.LifeCategory;

/**
 * POST /areas/score 요청 (API 문서 그대로). 가중치·직장 위치는 저장하거나 로그에 남기지 않아요.
 *
 * @param siteIds area 위치 ID들 (공고 목록·상세의 siteId)
 * @param priorities 항목별 가중치 0~10 (없는 항목은 0, 모두 0·없음이면 같은 비중)
 * @param workplace 직장 위치 (없으면 직장 항목 없이)
 */
public record AreaScoreRequest(
    @NotEmpty @Size(max = 50) List<@NotNull UUID> siteIds,
    @Valid Priorities priorities,
    @Valid Workplace workplace) {

  public record Priorities(
      @Min(0) @Max(10) Integer work,
      @Min(0) @Max(10) Integer transit,
      @Min(0) @Max(10) Integer school,
      @Min(0) @Max(10) Integer park,
      @Min(0) @Max(10) Integer convenience,
      @Min(0) @Max(10) Integer hospital) {

    public Map<LifeCategory, Integer> toMap() {
      Map<LifeCategory, Integer> out = new EnumMap<>(LifeCategory.class);
      put(out, LifeCategory.WORK, work);
      put(out, LifeCategory.TRANSIT, transit);
      put(out, LifeCategory.SCHOOL, school);
      put(out, LifeCategory.PARK, park);
      put(out, LifeCategory.CONVENIENCE, convenience);
      put(out, LifeCategory.HOSPITAL, hospital);
      return out;
    }

    private static void put(Map<LifeCategory, Integer> out, LifeCategory c, Integer w) {
      if (w != null) {
        out.put(c, w);
      }
    }
  }

  /**
   * @param label 화면에 보이는 이름 (예: 여의도역) — 계산에 안 써요
   */
  public record Workplace(
      String label,
      @NotNull @DecimalMin("-90") @DecimalMax("90") Double lat,
      @NotNull @DecimalMin("-180") @DecimalMax("180") Double lng) {

    public Coordinate toCoordinate() {
      return new Coordinate(lat, lng);
    }
  }
}
