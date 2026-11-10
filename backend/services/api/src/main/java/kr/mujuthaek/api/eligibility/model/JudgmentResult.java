package kr.mujuthaek.api.eligibility.model;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.List;
import kr.mujuthaek.api.eligibility.rule.Eligibility;
import kr.mujuthaek.api.eligibility.rule.Verdict;

/**
 * 판정 틀 하나의 판정 결과. result는 ELIGIBLE(지원 가능) / NEEDS_INPUT(확인 필요) / INELIGIBLE(지원 불가)이에요. 저장하지 않아요.
 *
 * <p>조건마다의 결과(MET / NOT_MET / UNKNOWN)와 기준 설명이 있어요. 사용자가 넣은 값(소득·자산·나이·매출)은 들어 있지 않아요.
 *
 * @param rank 내 순위: 충족한 대상군 중 가장 앞 신청 순위 (1이 가장 앞). 순위가 없는 공고·지원 가능이 아니면 null
 * @param common 공통 조건 결과
 * @param groups 대상군 결과 (rank는 공고가 정한 그 대상군의 신청 순위, result는 공통 조건까지 합친 결과로 ELIGIBLE / NEEDS_INPUT /
 *     INELIGIBLE, criteria는 그 대상군 조건만)
 * @param preferences 우대 결과 (MET = 우대 해당, UNKNOWN = 우대 확인 필요)
 * @param missingInputs 결과가 확인 필요일 때 넣으면 결과가 정해질 수 있는 입력 칸
 */
public record JudgmentResult(
    String field,
    Eligibility result,
    Integer rank,
    LocalDate referenceDate,
    List<Criterion> common,
    List<Group> groups,
    List<Preference> preferences,
    List<Note> notes,
    List<MissingInput> missingInputs) {

  /**
   * 조건 하나의 결과.
   *
   * @param summary 기준 설명 (예: 만 19~39세)
   * @param reason 충족이 아닌 이유 (충족이면 null)
   * @param needs 확인 필요일 때 넣으면 이 조건이 정해질 수 있는 입력 칸 (missingInputs의 field와 같은 이름). 검수 중이거나 입력으로 정할 수
   *     없는 조건(원문 확인)은 빈 목록이에요. 주거·혜택 판정의 needs와 같은 뜻이에요 (2026-10-29 QA)
   * @param options ANY_OF일 때 길마다의 결과
   */
  public record Criterion(
      String id,
      String kind,
      Verdict result,
      String summary,
      String reason,
      List<String> needs,
      String quote,
      Integer page,
      List<Option> options) {}

  public record Option(String label, Verdict result, List<Criterion> criteria) {}

  public record Group(
      String id, String name, Integer rank, Eligibility result, List<Criterion> criteria) {}

  public record Preference(
      String id,
      String label,
      String groupId,
      String effect,
      BigDecimal points,
      Verdict result,
      List<Criterion> criteria) {}

  public record Note(String kind, String groupId, String text, String quote, Integer page) {}
}
