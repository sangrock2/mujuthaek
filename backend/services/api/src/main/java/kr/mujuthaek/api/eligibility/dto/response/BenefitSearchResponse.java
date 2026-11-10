package kr.mujuthaek.api.eligibility.dto.response;

import java.time.LocalDate;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import kr.mujuthaek.api.eligibility.rule.Overall;

/**
 * 혜택 맞춤 목록 (POST /benefits/search). 지원 불가 혜택은 목록에서 빼고 개수만 줘요. 사용자가 보낸 값은 넣지 않아요.
 *
 * @param categoryCounts 분야별 지원 가능·확인 필요 혜택 수 (분야 필터를 걸기 전)
 */
public record BenefitSearchResponse(
    Summary summary,
    Map<String, Integer> categoryCounts,
    List<Item> items,
    String nextCursor,
    boolean hasNext) {

  /**
   * @param annualAmountWon 지원 가능한 혜택으로 1년에 받을 수 있는 돈 (금액이 정해진 지원만, 대출은 빼요)
   */
  public record Summary(int eligible, int needsInput, int ineligible, long annualAmountWon) {}

  /**
   * @param category HOUSING(주거) · ASSET(자산형성) · TRANSPORT(교통)
   * @param amountText 지원 내용 한 줄 ("월 최대 20만 원 · 12개월")
   * @param annualAmountWon 1년에 받을 수 있는 돈 (대출·금액 모름이면 0)
   * @param applyStatus UPCOMING · APPLYING · CLOSED · ALWAYS
   * @param affectsPrepareCost 보증금·구입 대출 혜택 (공고의 준비할 돈에 반영할 수 있어요)
   * @param needsReview 사람 확인 전 정책
   */
  public record Item(
      UUID id,
      String title,
      String agency,
      String category,
      String summary,
      List<String> regionNames,
      String amountText,
      long annualAmountWon,
      String applyStatus,
      LocalDate applyEnd,
      Integer dday,
      Overall overall,
      boolean affectsPrepareCost,
      boolean needsReview) {}
}
