package kr.mujuthaek.api.eligibility.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.UUID;
import kr.mujuthaek.api.eligibility.rule.DepositRegion;
import kr.mujuthaek.api.eligibility.rule.SubscriptionDeposits;

/** 청약 예치기준금액 한 칸 (4-08, 주택공급에 관한 규칙 별표 2). 표가 바뀌면 마이그레이션으로 시행일이 다른 행만 추가해요. 읽기만 해요. */
@Entity
@Table(schema = "eligibility", name = "subscription_deposits")
public class SubscriptionDeposit {

  @Id private UUID id;

  @Column(nullable = false)
  private LocalDate effectiveFrom;

  @Enumerated(EnumType.STRING)
  @Column(nullable = false)
  private DepositRegion region;

  private BigDecimal maxAreaM2;

  @Column(nullable = false)
  private long amountWon;

  @Column(nullable = false)
  private String source;

  protected SubscriptionDeposit() {}

  public SubscriptionDeposits.Row toRow() {
    return new SubscriptionDeposits.Row(effectiveFrom, region, maxAreaM2, amountWon);
  }
}
