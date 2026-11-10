package kr.mujuthaek.api.eligibility.rule;

import java.util.List;

/**
 * 조건 하나의 판정 결과. 사용자가 보낸 값(소득·자산 등)은 넣지 않고 기준과 결과만 담아요.
 *
 * @param key 조건 종류 (AGE, INCOME, CAR_VALUE …)
 * @param label 화면 문구 ("나이 · 만 19~39세")
 * @param reason 확인 필요·불충족의 이유 한 줄 (충족이면 null)
 * @param needs 이 조건을 판정하려면 넣어야 하는 입력 칸 (applicant.…)
 * @param threshold 소득처럼 기준 금액이 있는 조건의 기준
 * @param options 택일 조건(ANY_OF)의 선택지별 결과
 */
public record Item(
    String id,
    String key,
    String label,
    Status status,
    String reason,
    List<String> needs,
    Threshold threshold,
    Evidence evidence,
    List<OptionResult> options) {

  /** 근거 원문과 쪽. */
  public record Evidence(String text, Integer page) {}

  /** 소득 기준 (MEDIAN_INCOME 2026년 100%, 1인, 월 금액). */
  public record Threshold(
      String kind, Integer year, Double percent, Integer householdSize, Long amountWon) {}

  public record OptionResult(String label, Status status, List<Item> items) {}
}
