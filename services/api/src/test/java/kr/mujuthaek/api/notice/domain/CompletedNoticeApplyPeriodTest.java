package kr.mujuthaek.api.notice.domain;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.LocalDate;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.json.JsonMapper;

/** 공고 접수 기간: 전체 접수 일정이 없고 순위·대상별 접수 구간만 있으면 가장 이른 시작 ~ 가장 늦은 끝이에요. 합성 자료예요. */
class CompletedNoticeApplyPeriodTest {

  private static final JsonMapper JSON = JsonMapper.builder().build();

  private static LocalDate[] period(String payload) {
    return CompletedNotice.applyPeriod(JSON.readTree(payload));
  }

  @Test
  void 전체_접수_일정이_있으면_그_기간이다() {
    assertThat(
            period(
                """
                {"schedule":{"applyStartOn":"2026-11-03","applyEndOn":"2026-11-05"},
                 "applicationWindows":[{"applyStartOn":"2026-11-01","applyEndOn":"2026-11-30"}]}
                """))
        .containsExactly(LocalDate.of(2026, 11, 3), LocalDate.of(2026, 11, 5));
  }

  @Test
  void 순위별_접수_구간만_있으면_가장_이른_시작부터_가장_늦은_끝까지다() {
    assertThat(
            period(
                """
                {"schedule":null,
                 "applicationWindows":[
                   {"priorityRank":2,"applyStartOn":"2026-11-06","applyEndOn":"2026-11-07"},
                   {"priorityRank":1,"applyStartOn":"2026-11-03","applyEndOn":"2026-11-05"}]}
                """))
        .containsExactly(LocalDate.of(2026, 11, 3), LocalDate.of(2026, 11, 7));
  }

  @Test
  void 끝을_모르는_구간이_있으면_끝은_비운다() {
    assertThat(
            period(
                """
                {"applicationWindows":[
                   {"applyStartOn":"2026-11-03","applyEndOn":"2026-11-05"},
                   {"applyStartOn":null,"applyEndOn":null}]}
                """))
        .containsExactly(LocalDate.of(2026, 11, 3), null);
  }

  @Test
  void 보류해_빠진_접수_일정이_있으면_끝은_비운다() {
    // 2026-11-10 코드 검토: 보류한 2순위(10/05~10/07)가 접수 구간에서 빠져 마감이 10/03으로 보였고 마감 알림도 앞당겨졌음
    assertThat(
            period(
                """
                {"schedule":null,
                 "applicationWindows":[{"priorityRank":1,"applyStartOn":"2026-10-01","applyEndOn":"2026-10-03"}],
                 "notice":{"schedules":[
                   {"id":"rank1","kinds":["APPLICATION"]},
                   {"id":"rank2","kinds":["APPLICATION"]},
                   {"id":"winners","kinds":["WINNER_ANNOUNCEMENT"]}]}}
                """))
        .containsExactly(LocalDate.of(2026, 10, 1), null);
  }

  @Test
  void 접수_구간이_없으면_비어_있다() {
    assertThat(period("{}")).containsExactly(null, null);
    assertThat(period("{\"applicationWindows\":[]}")).containsExactly(null, null);
  }
}
