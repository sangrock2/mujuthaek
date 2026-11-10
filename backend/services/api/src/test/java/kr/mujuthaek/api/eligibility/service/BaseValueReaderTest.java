package kr.mujuthaek.api.eligibility.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import java.util.List;
import kr.mujuthaek.api.eligibility.domain.BaseValue;
import kr.mujuthaek.api.eligibility.repository.BaseValueRepository;
import kr.mujuthaek.api.eligibility.rule.BaseValueKind;
import org.junit.jupiter.api.Test;

/** 기준값 읽기: 소득 기준은 가구원 수 표에서, 자산 기준은 한 칸. 실제 DB·마이그레이션 값은 BaseValueMigrationTest에서 봐요. */
class BaseValueReaderTest {

  private final BaseValueRepository repository = mock(BaseValueRepository.class);
  private final BaseValueReader reader = new BaseValueReader(repository);

  private static BaseValue row(int householdSize, long amountWon) {
    BaseValue value = mock(BaseValue.class);
    when(value.householdSize()).thenReturn(householdSize);
    when(value.amountWon()).thenReturn(amountWon);
    return value;
  }

  @Test
  void incomeIsLookedUpByHouseholdSize() {
    List<BaseValue> rows = List.of(row(1, 100), row(2, 150));
    when(repository.findByKindAndYearAndProgram(BaseValueKind.MEDIAN_INCOME, 2026, ""))
        .thenReturn(rows);
    assertThat(reader.find(BaseValueKind.MEDIAN_INCOME, 2026, "", 2)).hasValue(150);
    assertThat(reader.find(BaseValueKind.MEDIAN_INCOME, 2026, "", 4)).hasValue(250);
    assertThat(reader.find(BaseValueKind.URBAN_WORKER_INCOME, 2026, "", 1)).isEmpty();
  }

  @Test
  void assetIsOneValuePerProgram() {
    List<BaseValue> rows = List.of(row(0, 45_630_000));
    when(repository.findByKindAndYearAndProgram(BaseValueKind.CAR_VALUE, 2026, "국민임대"))
        .thenReturn(rows);
    assertThat(reader.find(BaseValueKind.CAR_VALUE, 2026, "국민임대", 0)).hasValue(45_630_000);
    assertThat(reader.find(BaseValueKind.CAR_VALUE, 2026, "행복주택", 0)).isEmpty();
  }
}
