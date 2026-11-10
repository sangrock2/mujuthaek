package kr.mujuthaek.api.notice.mapper;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import tools.jackson.databind.json.JsonMapper;

/** API 대조 값 비교가 계약 검사기(Python ==)와 같은지. 다르면 계약을 통과한 이벤트가 실패 큐로 가요. */
class NoticeIntegrityCompareTest {

  private static final JsonMapper JSON = JsonMapper.builder().build();

  private static boolean same(String a, String b) {
    return NoticeIntegrity.sameJson(JSON.readTree(a), JSON.readTree(b));
  }

  @Test
  void 숫자는_값으로_비교한다() {
    assertThat(same("1", "1.0")).isTrue();
    assertThat(same("true", "1")).isTrue();
    assertThat(same("[1, {\"a\": 2.50}]", "[1.0, {\"a\": 2.5}]")).isTrue();
    assertThat(same("1", "2")).isFalse();
    assertThat(same("\"1\"", "1")).isFalse();
    assertThat(same("{\"a\": 1}", "{\"a\": 1, \"b\": null}")).isFalse();
    assertThat(same("null", "null")).isTrue();
  }
}
