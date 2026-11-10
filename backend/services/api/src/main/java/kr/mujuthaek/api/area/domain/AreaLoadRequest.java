package kr.mujuthaek.api.area.domain;

import java.time.LocalDate;
import java.util.Objects;

/**
 * 원천 파일 하나를 적재하는 요청.
 *
 * @param scope 상가정보는 시도 이름(강원, 경기 …), 나머지는 "ALL". 지우기는 이 범위 안에서만 해요.
 * @param fileKey S3 키 (area/{source}/{기준일}/{영문 파일 이름})
 * @param sha256 파일 지문. 같은 지문이 이미 성공했으면 건너뛰어요.
 * @param allowShrink 이전보다 행이 절반 넘게 줄어도 적재할지 (기본 false: 잘린 파일을 막으려고)
 */
public record AreaLoadRequest(
    AreaSource source,
    String scope,
    String fileKey,
    String sha256,
    LocalDate dataDate,
    boolean allowShrink) {

  public static final String ALL = "ALL";

  public AreaLoadRequest {
    Objects.requireNonNull(source, "source");
    Objects.requireNonNull(fileKey, "fileKey");
    Objects.requireNonNull(sha256, "sha256");
    Objects.requireNonNull(dataDate, "dataDate");
    scope = (scope == null || scope.isBlank()) ? ALL : scope.trim();
    if (source.scoped() && ALL.equals(scope)) {
      throw new IllegalArgumentException(source + "는 시도 파일마다 scope(예: 상가는 강원)를 줘야 해요");
    }
  }
}
