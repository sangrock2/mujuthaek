package kr.mujuthaek.api.eligibility.model;

/**
 * 넣으면 판정 결과가 정해질 수 있는 입력 칸.
 *
 * @param field 판정 입력(JudgmentApplicantRequest) 안의 칸 경로 (예: household.monthlyIncomeWon)
 * @param label 화면에 보일 이름
 */
public record MissingInput(String field, String label) {}
