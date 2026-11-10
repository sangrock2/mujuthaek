package kr.mujuthaek.api.eligibility.repository;

import java.util.List;
import java.util.UUID;
import kr.mujuthaek.api.eligibility.domain.BaseValue;
import kr.mujuthaek.api.eligibility.rule.BaseValueKind;
import org.springframework.data.jpa.repository.JpaRepository;

public interface BaseValueRepository extends JpaRepository<BaseValue, UUID> {

  List<BaseValue> findByKindAndYearAndProgram(BaseValueKind kind, int year, String program);
}
