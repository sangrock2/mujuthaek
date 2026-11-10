package kr.mujuthaek.api.benefit.service;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.List;
import java.util.UUID;

/**
 * 판정에 쓰는 혜택 한 건 (eligibility가 읽어요). 금액은 원이에요.
 *
 * @param category 화면 분야 HOUSING · ASSET · TRANSPORT
 * @param regionScope NATIONWIDE · SIDO · SIGUNGU · UNKNOWN
 * @param needsReview 사람 확인 전 (판정은 확인 필요를 넘지 않아요)
 * @param updatedAt 마지막으로 바뀐 시각. 혜택이 바뀌면(새 버전·상태) 달라져서 판정 캐시의 키로 써요
 */
public record BenefitForJudgment(
    UUID id,
    String title,
    String agency,
    String category,
    String summary,
    String regionScope,
    List<String> regionCodes,
    List<String> regionNames,
    LocalDate applyStart,
    LocalDate applyEnd,
    boolean applyAlways,
    boolean needsReview,
    List<Support> supports,
    List<Condition> conditions,
    java.time.Instant updatedAt) {

  /**
   * @param kind RENT · DEPOSIT_LOAN · PURCHASE_LOAN · HOUSING_SUPPLY · MOVE_IN_GRANT · CASH · OTHER
   *     …
   * @param amountMaxWon 최대 금액 (원, 모르면 null)
   * @param amountPer ONCE · MONTH · YEAR
   */
  public record Support(
      String kind,
      Long amountMaxWon,
      String amountPer,
      Integer months,
      BigDecimal ratePct,
      String rawText) {}

  /**
   * 자격 조건 한 줄 (benefit-condition-types.draft.md). 같은 group은 또는, 다른 group은 그리고.
   *
   * @param valueJson type마다 정해진 값 (JSON 글자). known=false면 null
   */
  public record Condition(
      String type, String valueJson, int group, boolean known, String rawText, String evidence) {}
}
