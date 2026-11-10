package kr.mujuthaek.api.eligibility.rule.frame;

import java.util.Collection;
import java.util.List;
import kr.mujuthaek.api.eligibility.rule.Verdict;

/**
 * 조건 하나의 판정 결과 (4-06의 "항목별 충족 여부").
 *
 * <p>summary와 reason에는 기준만 있고 사용자가 넣은 값(소득·자산·나이·매출)은 넣지 않아요.
 *
 * @param summary 기준을 사람이 읽게 쓴 것 (예: 만 19~39세, 월소득 3,432,027원 이하)
 * @param reason 충족이 아닌 이유 (예: 생년월일이 없어요, 검수 중). 충족이면 null
 * @param missing 확인 필요일 때 넣으면 판정할 수 있는 입력
 * @param options ANY_OF일 때 길마다의 결과, 아니면 빈 목록
 */
public record Evaluation(
    Criterion criterion,
    Verdict verdict,
    String summary,
    String reason,
    List<Input> missing,
    List<OptionResult> options) {

  public Evaluation {
    missing = List.copyOf(missing);
    options = List.copyOf(options);
  }

  /** ANY_OF의 길 하나: 그 안 조건을 모두 충족해야 충족. */
  public record OptionResult(String label, Verdict verdict, List<Evaluation> criteria) {
    public OptionResult {
      criteria = List.copyOf(criteria);
    }
  }

  static Evaluation met(Criterion criterion, String summary) {
    return new Evaluation(criterion, Verdict.MET, summary, null, List.of(), List.of());
  }

  static Evaluation notMet(Criterion criterion, String summary, String reason) {
    return new Evaluation(criterion, Verdict.NOT_MET, summary, reason, List.of(), List.of());
  }

  static Evaluation decided(Criterion criterion, boolean met, String summary) {
    return met ? met(criterion, summary) : notMet(criterion, summary, null);
  }

  static Evaluation unknown(
      Criterion criterion, String summary, String reason, Collection<Input> missing) {
    return new Evaluation(
        criterion, Verdict.UNKNOWN, summary, reason, List.copyOf(missing), List.of());
  }

  static Evaluation unknown(Criterion criterion, String summary, String reason, Input... missing) {
    return unknown(criterion, summary, reason, List.of(missing));
  }

  /**
   * 가공하면서 확신이 없었던 조건: 계산한 기준은 보여주되 충족은 확인 필요로 낮춰요. 입력만으로 걸리는 불충족은 그대로 둬요. 검수 이유(reviewReason)는 관리자용
   * 설명이라 회원 화면에 문구로 내보내지 않아요 (2026-10-29 QA)
   */
  Evaluation inReview() {
    if (verdict == Verdict.NOT_MET) {
      return this;
    }
    return new Evaluation(criterion, Verdict.UNKNOWN, summary, null, List.of(), options);
  }
}
