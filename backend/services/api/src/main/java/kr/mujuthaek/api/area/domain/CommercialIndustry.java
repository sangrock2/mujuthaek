package kr.mujuthaek.api.area.domain;

import java.util.Locale;
import java.util.Optional;

/**
 * 상권 점수에서 "같은 업종"으로 세는 묶음 (7단계, 계획 35번). 사업 입력 업종이 FOOD·CAFE·RETAIL이면 상가 업종 묶음과 이어지고, 그 밖의 업종은 같은
 * 업종이 없어요(경쟁 점수 없음).
 */
public enum CommercialIndustry {
  /** 음식점 묶음 (상가 industry_group FOOD) */
  FOOD,
  /** 카페 묶음 (상가 industry_group CAFE) */
  CAFE,
  /** 소매 대분류 G2 (상가 large_code G2) */
  RETAIL;

  public static Optional<CommercialIndustry> of(String code) {
    if (code == null || code.isBlank()) {
      return Optional.empty();
    }
    try {
      return Optional.of(valueOf(code.strip().toUpperCase(Locale.ROOT)));
    } catch (IllegalArgumentException e) {
      return Optional.empty();
    }
  }
}
