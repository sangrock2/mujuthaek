package kr.mujuthaek.api.benefit.domain;

import java.util.Collection;
import java.util.Set;

/**
 * 화면 분야 (내 혜택의 주거 · 자산형성 · 교통 칩). 출처 분류(categories)에 교통·자산형성 말이 있으면 그 분야, 그 밖은 주거예요. 주거
 * 지원(월세·보증금·구입 대출·집 제공·전입 지원금)이 있으면 출처 분류와 상관없이 주거로 봐요.
 */
public enum BenefitCategory {
  HOUSING,
  ASSET,
  TRANSPORT;

  private static final Set<String> HOUSING_SUPPORTS =
      Set.of("RENT", "DEPOSIT_LOAN", "PURCHASE_LOAN", "HOUSING_SUPPLY", "MOVE_IN_GRANT");

  public static BenefitCategory of(Collection<String> supportKinds, Collection<String> categories) {
    if (supportKinds.stream().anyMatch(HOUSING_SUPPORTS::contains)) return HOUSING;
    String joined = String.join(" ", categories);
    if (joined.contains("교통")) return TRANSPORT;
    if (joined.contains("자산") || joined.contains("저축") || joined.contains("금융")) return ASSET;
    return HOUSING;
  }
}
