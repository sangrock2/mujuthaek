package kr.mujuthaek.api.eligibility.service;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.OptionalLong;
import kr.mujuthaek.api.eligibility.domain.SubscriptionDeposit;
import kr.mujuthaek.api.eligibility.repository.SubscriptionDepositRepository;
import kr.mujuthaek.api.eligibility.rule.DepositRegion;
import kr.mujuthaek.api.eligibility.rule.SubscriptionDeposits;
import org.springframework.stereotype.Component;

/** 판정 코드(rule)에 청약 예치기준금액을 DB에서 읽어 줘요. 표가 작아서(시행일마다 12칸) 부를 때마다 모두 읽어요. */
@Component
class SubscriptionDepositReader implements SubscriptionDeposits {

  private final SubscriptionDepositRepository repository;

  SubscriptionDepositReader(SubscriptionDepositRepository repository) {
    this.repository = repository;
  }

  @Override
  public OptionalLong find(LocalDate day, DepositRegion region, BigDecimal exclusiveAreaM2) {
    return SubscriptionDeposits.pick(
        repository.findAll().stream().map(SubscriptionDeposit::toRow).toList(),
        day,
        region,
        exclusiveAreaM2);
  }
}
