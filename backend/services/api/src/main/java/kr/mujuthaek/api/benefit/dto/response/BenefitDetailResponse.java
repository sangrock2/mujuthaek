package kr.mujuthaek.api.benefit.dto.response;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.List;
import java.util.UUID;

/**
 * 혜택 상세 (GET /api/v1/benefits/{id}). 공개 정보만 있고 판정은 POST /api/v1/benefits/{id}/evaluate로 해요. 금액은
 * 원이에요.
 *
 * @param conditions 자격 조건 원문과 근거 (판정 결과는 없어요)
 * @param sources 원문·신청 주소 (같은 정책이 여러 출처에 있으면 나중에 여러 개)
 */
public record BenefitDetailResponse(
    Header header,
    List<Support> supports,
    String howToApply,
    List<String> documents,
    String contact,
    List<Condition> conditions,
    List<Source> sources) {

  /**
   * @param category HOUSING(주거) · ASSET(자산형성) · TRANSPORT(교통)
   * @param applyStatus UPCOMING · APPLYING · CLOSED · ALWAYS (오늘 날짜로 계산)
   * @param dday 마감까지 남은 날 (상시·마감일 모름이면 null)
   * @param needsReview 사람 확인 전 정책 (판정은 확인 필요를 넘지 않아요)
   */
  public record Header(
      UUID id,
      String title,
      String agency,
      String category,
      String summary,
      String regionScope,
      List<String> regionNames,
      List<String> regionCodes,
      String applyStatus,
      LocalDate applyStart,
      LocalDate applyEnd,
      Integer dday,
      LocalDate businessStart,
      LocalDate businessEnd,
      String scheduleText,
      boolean needsReview) {}

  /**
   * @param kind RENT(월세) · DEPOSIT_LOAN(보증금 대출) · PURCHASE_LOAN(구입 대출) · HOUSING_SUPPLY(집 제공) ·
   *     MOVE_IN_GRANT(전입·정착 지원금) · CASH · OTHER
   * @param amountMaxWon 최대 금액 (원, 모르면 null)
   * @param amountPer ONCE · MONTH · YEAR
   */
  public record Support(
      String kind,
      Long amountMaxWon,
      String amountPer,
      Integer months,
      BigDecimal ratePct,
      String rawText,
      String evidence) {}

  /** 자격 조건 한 줄. 같은 group은 또는, 다른 group은 그리고. */
  public record Condition(String type, int group, boolean known, String rawText, String evidence) {}

  public record Source(String sourceCode, String detailUrl, String applyUrl) {}
}
