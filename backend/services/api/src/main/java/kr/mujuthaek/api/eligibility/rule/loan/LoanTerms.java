package kr.mujuthaek.api.eligibility.rule.loan;

import java.time.LocalDate;

/**
 * 대출 상품 하나의 한 시점 자격 조건. 값은 eligibility.loan_rules 표에서 읽어요. null인 칸은 그 조건이 없다는 뜻이에요.
 *
 * <p>칸 뜻은 마이그레이션 V202610241830__eligibility_create_loan_rules.sql의 주석과 같아요. 집이 정해져야 보는 조건(보증금 상한,
 * 면적, 담보 평가액)은 없어요. 판정은 공고와 상관없이 사람 조건만 봐요.
 *
 * @param newlywedMaxYears 신혼부부 = 혼인 N년 이내 (3개월 안 결혼 예정 포함). 신혼 필수·신혼 소득 예외에 써요
 * @param maxApplicantIncomeWon 신혼가구가 부부합산 상한을 넘어도 신청인 1인 연소득이 이 이하면 가능
 * @param unverifiableRequirement 사용자 입력으로 알 수 없는 조건. 있으면 나머지가 모두 맞아도 확인 필요예요
 * @param limitSummary 화면에 보여 줄 한도 요약 (판정에는 안 써요)
 * @param rateSummary 화면에 보여 줄 금리 요약 (판정에는 안 써요)
 */
public record LoanTerms(
    String productCode,
    String productName,
    LoanType loanType,
    int displayOrder,
    LocalDate effectiveFrom,
    Integer minAge,
    Integer maxAge,
    boolean singleHouseholderRequired,
    boolean under30SingleExcluded,
    boolean newlywedRequired,
    Integer newlywedMaxYears,
    Integer newbornWithinMonths,
    LocalDate newbornBornSince,
    boolean firstHomeRequired,
    long maxIncomeWon,
    Long maxIncomeNewlywedWon,
    Long maxIncomeTwoChildrenWon,
    Long maxIncomeFirstHomeWon,
    Long maxIncomeDualWon,
    Long maxEachIncomeWon,
    Long maxApplicantIncomeWon,
    long maxNetAssetWon,
    String unverifiableRequirement,
    String limitSummary,
    String rateSummary,
    String sourceUrl) {}
