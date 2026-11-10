package kr.mujuthaek.api.notice.service;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.LocalDate;
import java.util.List;
import java.util.UUID;
import kr.mujuthaek.api.notice.repository.NoticeQueries.PolicySummaryRow;
import org.junit.jupiter.api.Test;

/** 정책 신청 상태: 판정 목록(openPolicies)과 같은 규칙. */
class PolicyStatusTest {

  private static final LocalDate TODAY = LocalDate.of(2026, 11, 10);

  private static PolicySummaryRow row(LocalDate end, boolean always, String applyNote) {
    return new PolicySummaryRow(
        UUID.randomUUID(),
        1,
        "STARTUP_SUPPORT",
        "가상 창업 지원",
        null,
        null,
        end,
        always,
        List.of(),
        null,
        applyNote);
  }

  @Test
  void aPolicyOpenUntilTheBudgetRunsOutIsApplying() {
    // 2026-11-10 코드 검토: 마감일 없이 「예산 소진 시까지」인 정책은 openPolicies에는 열린 정책인데 UNKNOWN이라 새 정책 알림이 가지 않았음
    assertThat(NoticeQueryService.policyStatus(row(null, false, "예산 소진 시까지"), TODAY))
        .isEqualTo("APPLYING");
    assertThat(NoticeQueryService.policyStatus(row(null, false, null), TODAY)).isEqualTo("UNKNOWN");
    assertThat(NoticeQueryService.policyStatus(row(null, true, null), TODAY)).isEqualTo("ALWAYS");
    assertThat(NoticeQueryService.policyStatus(row(TODAY.minusDays(1), false, null), TODAY))
        .isEqualTo("CLOSED");
  }
}
