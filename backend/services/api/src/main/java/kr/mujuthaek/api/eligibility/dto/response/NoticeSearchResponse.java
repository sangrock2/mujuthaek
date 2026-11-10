package kr.mujuthaek.api.eligibility.dto.response;

import java.time.LocalDate;
import java.util.List;
import java.util.UUID;
import kr.mujuthaek.api.eligibility.rule.Overall;

/**
 * 맞춤 목록 (POST /notices/search). counts는 지원 불가를 빼기 전 전체 개수예요 (화면의 "지원 가능 7곳").
 *
 * <p>favorite는 로그인이 생기면 채워요 (지금은 null).
 */
public record NoticeSearchResponse(
    Counts counts, List<Item> items, String nextCursor, boolean hasNext) {

  public record Counts(int eligible, int needsInput, int ineligible) {}

  /**
   * @param postedOn 공고일 (모르면 null)
   * @param prepareCostWon 주택형 중 가장 적은 준비할 돈 (모르면 null)
   * @param areaScore 위치 중 가장 높은 생활권 총점 (공고 목록과 같음, 없으면 null)
   * @param tags·lat·lng·siteCount 대표 위치의 세권 태그·좌표, 위치 수 (공고 목록과 같음)
   * @param prepareCostNote prepareCostWon이 null인 이유 (ASSET_UNKNOWN · INCOME_UNKNOWN ·
   *     PRICE_NOT_ANNOUNCED …)
   */
  public record Item(
      UUID id,
      String title,
      String provider,
      String noticeType,
      String regionCode,
      String regionName,
      String status,
      LocalDate applyStart,
      LocalDate applyEnd,
      Integer dday,
      LocalDate postedOn,
      Overall overall,
      Long prepareCostWon,
      String prepareCostNote,
      Integer areaScore,
      Boolean favorite,
      List<String> tags,
      Double lat,
      Double lng,
      int siteCount) {}
}
