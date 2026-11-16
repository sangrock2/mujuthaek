package kr.mujuthaek.api.eligibility.service;

import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verifyNoInteractions;

import java.time.Clock;
import kr.mujuthaek.api.common.exception.CustomException;
import kr.mujuthaek.api.eligibility.repository.CriteriaStore;
import kr.mujuthaek.api.eligibility.repository.LoanProductStore;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.json.JsonMapper;

class CriteriaYearBoundaryTest {
  @Test
  void unsupportedYearsAreRejectedBeforeQueriesOrArithmetic() {
    CriteriaStore store = mock(CriteriaStore.class);
    LoanProductStore loans = mock(LoanProductStore.class);
    CriteriaService service =
        new CriteriaService(store, loans, JsonMapper.builder().build(), Clock.systemUTC());
    for (int year : new int[] {Integer.MIN_VALUE, Integer.MAX_VALUE, 1999, 2201}) {
      assertThatThrownBy(() -> service.criteria(year, null)).isInstanceOf(CustomException.class);
    }
    verifyNoInteractions(store, loans);
  }
}
