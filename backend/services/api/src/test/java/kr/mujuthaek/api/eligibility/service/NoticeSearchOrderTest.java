package kr.mujuthaek.api.eligibility.service;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.LocalDate;
import java.util.List;
import java.util.UUID;
import kr.mujuthaek.api.eligibility.dto.response.NoticeSearchResponse;
import kr.mujuthaek.api.eligibility.rule.Overall;
import org.junit.jupiter.api.Test;

/** 맞춤 목록 순서 (9단계): RECOMMENDED는 판정 → 마감 임박 → 생활권 총점, AREA_SCORE는 총점만. */
class NoticeSearchOrderTest {

  private static NoticeSearchResponse.Item item(
      String id, Overall overall, String applyEnd, Integer areaScore) {
    return new NoticeSearchResponse.Item(
        UUID.fromString("00000000-0000-0000-0000-00000000000" + id),
        id,
        "LH",
        "HAPPY_HOUSING",
        "11680",
        "서울 강남구",
        "OPEN",
        null,
        applyEnd == null ? null : LocalDate.parse(applyEnd),
        null,
        null,
        overall,
        null,
        null,
        areaScore,
        null,
        List.of(),
        null,
        null,
        0);
  }

  private static List<String> sorted(String sort, NoticeSearchResponse.Item... items) {
    return java.util.Arrays.stream(items)
        .sorted(NoticeSearchService.order(sort))
        .map(NoticeSearchResponse.Item::title)
        .toList();
  }

  @Test
  void recommendedUsesTheAreaScoreOnlyAfterJudgmentAndDeadline() {
    var lowScoreSoon = item("1", Overall.ELIGIBLE, "2026-11-01", 40);
    var highScoreSameDay = item("2", Overall.ELIGIBLE, "2026-11-01", 90);
    var noScoreSameDay = item("3", Overall.ELIGIBLE, "2026-11-01", null);
    var highScoreLater = item("4", Overall.ELIGIBLE, "2026-11-20", 99);
    var needsInputSoonest = item("5", Overall.NEEDS_INPUT, "2026-10-26", 100);

    assertThat(
            sorted(
                "RECOMMENDED",
                needsInputSoonest,
                highScoreLater,
                noScoreSameDay,
                lowScoreSoon,
                highScoreSameDay))
        .containsExactly("2", "1", "3", "4", "5");
  }

  @Test
  void areaScoreSortsByTheTotalAloneWithUnknownLast() {
    var eligibleLow = item("1", Overall.ELIGIBLE, "2026-10-26", 40);
    var needsInputHigh = item("2", Overall.NEEDS_INPUT, "2026-12-01", 95);
    var unknown = item("3", Overall.ELIGIBLE, "2026-10-26", null);
    var tieA = item("4", Overall.ELIGIBLE, null, 70);
    var tieB = item("5", Overall.INELIGIBLE, "2026-10-27", 70);

    assertThat(sorted("AREA_SCORE", unknown, tieB, eligibleLow, needsInputHigh, tieA))
        .containsExactly("2", "4", "5", "1", "3"); // 같은 점수는 id 순 (커서가 흔들리지 않게)
  }
}
