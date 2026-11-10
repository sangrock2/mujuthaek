package kr.mujuthaek.api.notice.mapper;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

/** 공고 전체 신청 방법 계산 (Python 계약 검사기 application_channels와 같은 규칙). */
class NoticeProjectionChannelsTest {

  private static final JsonMapper JSON = JsonMapper.builder().build();

  private static JsonNode detail(String schedules) {
    return JSON.readTree("{\"schedules\":" + schedules + "}");
  }

  @Test
  void 신청_일정의_방법을_정해진_순서로_합친다() {
    JsonNode detail =
        detail(
            "[{\"kinds\":[\"APPLICATION\"],\"channels\":[\"ONSITE\"]},"
                + "{\"kinds\":[\"APPLICATION\"],\"channels\":[\"ONLINE\"]},"
                + "{\"kinds\":[\"CONTRACT\"],\"channels\":[\"MAIL\"]}]");

    assertThat(NoticeProjection.applicationChannels(detail)).containsExactly("ONLINE", "ONSITE");
  }

  @Test
  void 신청_일정이_없으면_계약_일정의_방법을_쓴다() {
    // 선착순 계약형 공고: 신청 단계 없이 계약으로 바로 받아요
    JsonNode detail =
        detail(
            "[{\"kinds\":[\"ANNOUNCEMENT\"],\"channels\":[]},"
                + "{\"kinds\":[\"CONTRACT\"],\"channels\":[\"ONSITE\"]}]");

    assertThat(NoticeProjection.applicationChannels(detail)).containsExactly("ONSITE");
  }
}
