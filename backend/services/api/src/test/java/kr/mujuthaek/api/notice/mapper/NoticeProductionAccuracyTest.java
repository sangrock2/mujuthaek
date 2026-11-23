package kr.mujuthaek.api.notice.mapper;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.LocalDate;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.json.JsonMapper;

class NoticeProductionAccuracyTest {
  private final JsonMapper json = JsonMapper.builder().build();

  @Test
  void displaysTheMinimumPeriodFromTheSource() {
    var condition =
        json.readTree(
            """
        {
          "category": "RESIDENCE",
          "description": "공고일 현재 금천구에 거주해야 해요.",
          "originalText": "공고일 현재 금천구에 2년 이상 거주하는"
        }
        """);
    assertThat(NoticeDetailMapper.residenceDescription(condition)).contains("2년 이상 거주");
  }

  @Test
  void removesOnlyLaterApplicationWindowsWithoutShiftingHeldIndexes() {
    var payload =
        json.readTree(
            """
        {"notice":{"schedules":[
          {"kinds":["APPLICATION"],"startsAt":{"value":"2026-11-23T10:00:00+09:00"}},
          {"kinds":["APPLICATION"],"startsAt":{"value":"2026-11-24T10:00:00+09:00"}},
          {"kinds":["DOCUMENT_SUBMISSION"],"startsAt":{"value":"2026-12-07"}}
        ]}}
        """);
    NoticeDetailMapper.excludeCancelledApplications(payload, LocalDate.of(2026, 11, 23));
    var schedules = payload.path("notice").path("schedules");
    assertThat(schedules.size()).isEqualTo(3);
    assertThat(schedules.get(0).isObject()).isTrue();
    assertThat(schedules.get(1).isNull()).isTrue();
    assertThat(schedules.get(2).path("kinds").get(0).asString()).isEqualTo("DOCUMENT_SUBMISSION");
  }
}
