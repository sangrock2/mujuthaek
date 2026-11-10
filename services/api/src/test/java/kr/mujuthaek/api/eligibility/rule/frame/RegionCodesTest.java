package kr.mujuthaek.api.eligibility.rule.frame;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import kr.mujuthaek.api.eligibility.rule.Verdict;
import org.junit.jupiter.api.Test;

class RegionCodesTest {

  @Test
  void aCityWithDistrictsContainsItsDistrictsAndOnlyThose() {
    // 2026-11-10 코드 검토: 수원시(41110)의 장안구(41111)는 앞부분이 시와 달라 「수원시 거주」 조건에서 불충족이 됐음
    assertThat(RegionCodes.within("41111", "4111000000")).isEqualTo(Verdict.MET);
    assertThat(RegionCodes.within("4111112300", "4111000000")).isEqualTo(Verdict.MET);
    assertThat(RegionCodes.within("41110", "4111100000"))
        .isEqualTo(Verdict.UNKNOWN); // 시만 넣었는데 조건이 그 시의 구
    assertThat(RegionCodes.within("41000", "4111100000")).isEqualTo(Verdict.UNKNOWN); // 시도만 넣음
    assertThat(RegionCodes.within("41113", "4111100000")).isEqualTo(Verdict.NOT_MET); // 같은 시의 다른 구
    assertThat(RegionCodes.within("41280", "4111000000")).isEqualTo(Verdict.NOT_MET); // 다른 시
    assertThat(RegionCodes.within("11140", "1111000000"))
        .isEqualTo(Verdict.NOT_MET); // 끝자리 0인 보통 구끼리
    assertThat(RegionCodes.withinAny("41111", List.of("1100000000", "4111000000")))
        .isEqualTo(Verdict.MET);
  }
}
