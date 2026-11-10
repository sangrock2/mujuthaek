package kr.mujuthaek.api.eligibility.service;

import java.util.Map;
import java.util.OptionalLong;
import java.util.stream.Collectors;
import kr.mujuthaek.api.eligibility.domain.BaseValue;
import kr.mujuthaek.api.eligibility.repository.BaseValueRepository;
import kr.mujuthaek.api.eligibility.rule.BaseValueKind;
import kr.mujuthaek.api.eligibility.rule.BaseValues;
import org.springframework.stereotype.Component;

/** 판정 코드(rule)에 기준값을 DB에서 읽어 줘요. */
@Component
class BaseValueReader implements BaseValues {

  private final BaseValueRepository repository;

  BaseValueReader(BaseValueRepository repository) {
    this.repository = repository;
  }

  @Override
  public OptionalLong find(BaseValueKind kind, int year, String program, int householdSize) {
    var rows = repository.findByKindAndYearAndProgram(kind, year, program);
    if (!kind.byHouseholdSize()) {
      return rows.stream().mapToLong(BaseValue::amountWon).findFirst();
    }
    Map<Integer, Long> table =
        rows.stream().collect(Collectors.toMap(BaseValue::householdSize, BaseValue::amountWon));
    return BaseValues.byHouseholdSize(table, householdSize);
  }
}
