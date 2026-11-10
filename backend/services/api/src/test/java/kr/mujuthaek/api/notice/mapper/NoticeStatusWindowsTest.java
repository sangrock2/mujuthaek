package kr.mujuthaek.api.notice.mapper;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.List;
import kr.mujuthaek.api.notice.domain.ApplicationStatusCalculator;
import kr.mujuthaek.api.notice.domain.ApplicationStatusCalculator.Window;
import kr.mujuthaek.api.notice.domain.NoticeStatus;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

/** 원문 일정(상세)으로 접수 상태 계산용 구간을 만드는 규칙 (리뷰 2026-10-22). */
class NoticeStatusWindowsTest {

  private static final JsonMapper JSON = JsonMapper.builder().build();

  private static Instant korea(String dateTime) {
    return LocalDateTime.parse(dateTime).atZone(ApplicationStatusCalculator.KOREA).toInstant();
  }

  private static JsonNode detail(String heldItems) {
    return JSON.readTree(
        """
        {"schedules": [
          {"id": "s1", "kinds": ["APPLICATION"], "rawLabel": "1차 접수",
           "startsAt": {"precision": "DAY", "value": "2026-10-20"},
           "endsAt": {"precision": "MINUTE", "value": "2026-10-21T17:00:00+09:00"},
           "scope": {"level": "NOTICE", "resolution": "RESOLVED", "targetGroups": []}},
          {"id": "s2", "kinds": ["APPLICATION"], "rawLabel": "추가 접수",
           "startsAt": {"precision": "DAY", "value": "2026-10-23"},
           "endsAt": {"precision": "DAY", "value": "2026-10-23"},
           "scope": {"level": "NOTICE", "resolution": "RESOLVED", "targetGroups": []}}
         ],
         "quality": {"heldItems": %s, "reviewIssues": [], "notes": []}}
        """
            .formatted(heldItems));
  }

  @Test
  void 원문에_마감_시각이_있으면_그_시각까지만_접수_중이다() {
    // 날짜만 보면 17시 마감인데 같은 날 18시에도 접수 중이었음
    List<Window> windows = NoticeProjection.statusWindows(detail("[]"), false);

    assertThat(
            ApplicationStatusCalculator.calculate(windows, false, korea("2026-10-21T16:59"))
                .status())
        .isEqualTo(NoticeStatus.APPLYING);
    var after = ApplicationStatusCalculator.calculate(windows, false, korea("2026-10-21T18:00"));
    assertThat(after.status()).isEqualTo(NoticeStatus.UPCOMING); // 추가 접수(10/23)가 남음
    assertThat(
            ApplicationStatusCalculator.calculate(windows, false, korea("2026-10-21T16:00"))
                .nextCheckAt())
        .isEqualTo(korea("2026-10-21T17:01"));
  }

  @Test
  void 보류된_접수_구간이_남아_있으면_끝난_구간만으로_마감하지_않는다() {
    // 끝난 확정 구간과 보류된 추가 접수 구간이 함께 있을 때 마감(CLOSED)으로 확정했음
    List<Window> held =
        NoticeProjection.statusWindows(
            detail(
                """
                [{"target": "/schedules/1", "extent": "ITEM", "codes": ["VALUE_NOT_IN_QUOTE"], "description": "확인 전까지 보류"}]
                """),
            false);
    assertThat(
            ApplicationStatusCalculator.calculate(held, false, korea("2026-10-22T10:00")).status())
        .isEqualTo(NoticeStatus.UNKNOWN);
    assertThat(
            ApplicationStatusCalculator.calculate(held, false, korea("2026-10-30T10:00")).status())
        .isEqualTo(NoticeStatus.UNKNOWN);

    // 승인된 결과는 사람이 확인했으므로 보류 구간도 씀
    List<Window> approved = NoticeProjection.statusWindows(detail("[]"), true);
    assertThat(
            ApplicationStatusCalculator.calculate(approved, false, korea("2026-10-30T10:00"))
                .status())
        .isEqualTo(NoticeStatus.CLOSED);
    assertThat(approved.getFirst().endOn()).isEqualTo(LocalDate.of(2026, 10, 21));
  }
}
