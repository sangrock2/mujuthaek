package kr.mujuthaek.api.eligibility.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.LocalDate;
import java.util.UUID;
import kr.mujuthaek.api.eligibility.rule.loan.LoanTerms;
import kr.mujuthaek.api.eligibility.rule.loan.LoanType;

/** 대출 상품 하나의 한 시점 자격 조건. 조건이 바뀌면 마이그레이션으로 시행일이 다른 행만 추가해요. 읽기만 하고 앱에서 바꾸지 않아요. */
@Entity
@Table(schema = "eligibility", name = "loan_rules")
public class LoanProduct {

  @Id private UUID id;

  @Column(nullable = false)
  private String productCode;

  @Column(nullable = false)
  private String productName;

  @Enumerated(EnumType.STRING)
  @Column(nullable = false)
  private LoanType loanType;

  @Column(nullable = false)
  private int displayOrder;

  @Column(nullable = false)
  private LocalDate effectiveFrom;

  private Integer minAge;
  private Integer maxAge;

  @Column(nullable = false)
  private boolean singleHouseholderRequired;

  @Column(name = "under30_single_excluded", nullable = false)
  private boolean under30SingleExcluded;

  @Column(nullable = false)
  private boolean newlywedRequired;

  private Integer newlywedMaxYears;
  private Integer newbornWithinMonths;
  private LocalDate newbornBornSince;

  @Column(nullable = false)
  private boolean firstHomeRequired;

  @Column(nullable = false)
  private long maxIncomeWon;

  private Long maxIncomeNewlywedWon;
  private Long maxIncomeTwoChildrenWon;
  private Long maxIncomeFirstHomeWon;
  private Long maxIncomeDualWon;
  private Long maxEachIncomeWon;
  private Long maxApplicantIncomeWon;

  @Column(nullable = false)
  private long maxNetAssetWon;

  private String unverifiableRequirement;

  @Column(nullable = false)
  private String limitSummary;

  @Column(nullable = false)
  private String rateSummary;

  @Column(nullable = false)
  private String sourceUrl;

  protected LoanProduct() {}

  public LoanTerms toTerms() {
    return new LoanTerms(
        productCode,
        productName,
        loanType,
        displayOrder,
        effectiveFrom,
        minAge,
        maxAge,
        singleHouseholderRequired,
        under30SingleExcluded,
        newlywedRequired,
        newlywedMaxYears,
        newbornWithinMonths,
        newbornBornSince,
        firstHomeRequired,
        maxIncomeWon,
        maxIncomeNewlywedWon,
        maxIncomeTwoChildrenWon,
        maxIncomeFirstHomeWon,
        maxIncomeDualWon,
        maxEachIncomeWon,
        maxApplicantIncomeWon,
        maxNetAssetWon,
        unverifiableRequirement,
        limitSummary,
        rateSummary,
        sourceUrl);
  }
}
