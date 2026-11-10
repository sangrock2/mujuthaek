package kr.mujuthaek.api.eligibility.dto.response;

import java.time.LocalDate;
import java.util.List;
import java.util.UUID;
import kr.mujuthaek.api.eligibility.rule.Overall;

/**
 * 홈 요약 (POST /home/summary). 내 조건으로 판정한 공고에서 홈 카드에 쓰는 값만 골라요. 지원 불가 공고는 소식·마감 목록에 넣지 않아요.
 *
 * <p>생활권 점수는 공고별로만 보여 줘서 홈 요약에는 없어요.
 *
 * @param homes 공고 개수 요약
 * @param benefits 혜택 개수와 1년에 받을 수 있는 돈 (찾아볼 지역 기준)
 * @param suggestedBenefit 지원 가능한 혜택 중 1년에 받는 돈이 가장 많은 것 (없으면 null)
 * @param news 새로 올라온 공고 (공고일 최신순, 최대 {@code NEWS_SIZE}개)
 * @param deadlines 마감이 가까운 공고 (2주 안, 마감 임박순, 최대 {@code DEADLINE_SIZE}개)
 */
public record HomeSummaryResponse(
    Homes homes,
    Benefits benefits,
    SuggestedBenefit suggestedBenefit,
    List<Notice> news,
    List<Notice> deadlines) {

  /**
   * @param newThisWeek 지원 가능·확인 필요 중 최근 7일 안에 올라온 공고 수
   * @param closingSoon 지원 가능·확인 필요 중 7일 안에 마감하는 공고 수
   */
  public record Homes(
      int eligible, int needsInput, int ineligible, int newThisWeek, int closingSoon) {}

  /**
   * @param annualAmountWon 지원 가능한 혜택으로 1년에 받을 수 있는 돈 (금액이 정해진 지원만, 대출 제외)
   */
  public record Benefits(int eligible, int needsInput, long annualAmountWon) {}

  public record SuggestedBenefit(UUID id, String title, String amountText) {}

  public record Notice(
      UUID id,
      String title,
      String provider,
      String noticeType,
      String regionName,
      String status,
      LocalDate postedOn,
      LocalDate applyEnd,
      Integer dday,
      Overall overall) {}
}
