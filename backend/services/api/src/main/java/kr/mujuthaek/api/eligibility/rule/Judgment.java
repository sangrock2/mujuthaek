package kr.mujuthaek.api.eligibility.rule;

import java.time.LocalDate;
import java.util.List;

/**
 * 판정 틀 (contracts/schemas/housing-judgment.v1.json). extraction이 공고의 자격 조건을 판정하기 좋게 한 번 더 가공한 것이에요.
 *
 * @param referenceDate 나이·기간을 세는 기준일 (공고일·신청일 등)
 * @param common 모든 공급 대상에 공통인 조건
 * @param groups 공급 대상(청년·신혼부부 …)별 조건. 대상 하나라도 지원 가능하면 공고는 지원 가능
 */
public record Judgment(LocalDate referenceDate, List<Criterion> common, List<Group> groups) {

  public record Group(String id, String name, List<Criterion> criteria) {}

  /** 모든 조건이 같이 가진 칸. inReview면 불충족만 그대로 두고 나머지는 "확인 필요"로 둬요. */
  public record Basics(
      String id, String quote, Integer page, boolean inReview, String reviewReason) {}

  /** 조건 하나. 종류마다 판정에 쓰는 칸이 달라요. */
  public sealed interface Criterion {
    Basics basics();
  }

  public record Age(Basics basics, Integer minAge, Integer maxAge) implements Criterion {}

  /**
   * @param regionCodes 법정동코드 10자리 (모르는 하위 단계는 0)
   */
  public record Residence(Basics basics, List<String> regionCodes, Integer minMonths)
      implements Criterion {}

  /**
   * @param scope HOUSEHOLD 세대 전원 · APPLICANT 본인
   */
  public record Homeless(Basics basics, String scope, Integer minYears) implements Criterion {}

  /**
   * @param basis HOUSEHOLD · APPLICANT · APPLICANT_AND_PARENTS · HOUSEHOLD_IF_HEAD
   * @param standard MEDIAN_INCOME · URBAN_WORKER_INCOME · URBAN_WORKER_AVERAGE_INCOME
   * @param printedTable 공고에 인쇄된 가구원 수별 월 상한액 (있으면 이걸로 판정)
   */
  public record Income(
      Basics basics,
      String basis,
      String standard,
      Integer year,
      Double percent,
      List<Bonus> bonuses,
      String bonusCombine,
      List<PrintedRow> printedTable)
      implements Criterion {}

  public record Asset(Basics basics, String basis, long maxWon, List<Override> overrides)
      implements Criterion {}

  public record Car(Basics basics, long maxWon, List<Override> overrides) implements Criterion {}

  /**
   * @param require MARRIED · NOT_MARRIED
   */
  public record Marriage(Basics basics, String require, Integer maxYears, boolean allowEngaged)
      implements Criterion {}

  public record Children(
      Basics basics, Integer minCount, Integer youngestMaxAge, boolean includeUnborn)
      implements Criterion {}

  public record Savings(
      Basics basics,
      Integer minMonths,
      Integer minPayments,
      Long minBalanceWon,
      Double depositAreaM2)
      implements Criterion {}

  /**
   * @param anyOf 이 중 하나에 해당 (LIVELIHOOD_BENEFIT, NEAR_POOR, SINGLE_PARENT, UNIVERSITY_STUDENT …)
   */
  public record WelfareStatus(Basics basics, List<String> anyOf) implements Criterion {}

  /** 선택지 중 하나를 만족 (선택지 안의 조건은 모두 만족). */
  public record AnyOf(Basics basics, List<Option> options) implements Criterion {}

  public record Option(String label, List<Criterion> criteria) {}

  /** 입력 칸으로 판정할 수 없어 사용자에게 직접 묻는 조건. */
  public record Ask(Basics basics, String question, String metWhen) implements Criterion {}

  /** 금액 기준이 바뀌거나 비율이 더해지는 조건 (가구원 수, 자녀 수 …). */
  public record Factor(String factor, Integer min, Integer max) {}

  public record Bonus(Factor when, double addPercent) {}

  public record Override(Factor when, long maxWon) {}

  public record PrintedRow(int householdSize, long maxWon) {}
}
