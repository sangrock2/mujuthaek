package kr.mujuthaek.api.eligibility.dto.request;

import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import java.time.LocalDate;

/**
 * 규제지역 지정.
 *
 * @param regionCode 시군구 5자리 (시도 전체면 xx000)
 * @param kind SPECULATION_OVERHEATED 투기과열지구 · ADJUSTMENT_TARGET 조정대상지역 · SPECULATION 투기지역
 * @param scopeNote 일부 지역만이면 그 설명
 * @param validUntil 해제일 (지정 중이면 비움)
 */
public record RegulatedAreaRequest(
    @NotNull @Pattern(regexp = "^[0-9]{5}$") String regionCode,
    @NotNull Kind kind,
    @Size(max = 300) String scopeNote,
    @NotNull LocalDate validFrom,
    LocalDate validUntil,
    @Size(max = 300) String source) {

  public enum Kind {
    SPECULATION_OVERHEATED,
    ADJUSTMENT_TARGET,
    SPECULATION
  }
}
