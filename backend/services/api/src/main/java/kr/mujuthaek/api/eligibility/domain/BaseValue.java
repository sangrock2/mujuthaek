package kr.mujuthaek.api.eligibility.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.util.UUID;
import kr.mujuthaek.api.eligibility.rule.BaseValueKind;

/** 판정 기준값 한 칸 (4-08). 연도가 바뀌면 마이그레이션으로 행만 추가해요. 읽기만 하고 앱에서 바꾸지 않아요. */
@Entity
@Table(schema = "eligibility", name = "base_values")
public class BaseValue {

  @Id private UUID id;

  @Enumerated(EnumType.STRING)
  @Column(nullable = false)
  private BaseValueKind kind;

  @Column(nullable = false)
  private int year;

  @Column(nullable = false)
  private String program;

  @Column(nullable = false)
  private int householdSize;

  @Column(nullable = false)
  private long amountWon;

  @Column(nullable = false)
  private String source;

  protected BaseValue() {}

  public int householdSize() {
    return householdSize;
  }

  public long amountWon() {
    return amountWon;
  }
}
