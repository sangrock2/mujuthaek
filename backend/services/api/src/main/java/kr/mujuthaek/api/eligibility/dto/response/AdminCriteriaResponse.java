package kr.mujuthaek.api.eligibility.dto.response;

import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.util.List;
import tools.jackson.databind.JsonNode;

/**
 * 관리자 기준값 화면: 한 종류의 연도별 값과 바꾼 기록.
 *
 * @param kind MEDIAN_INCOME · URBAN_WORKER_INCOME · RANK_CRITERIA
 */
public record AdminCriteriaResponse(String kind, List<Year> years) {

  /**
   * 한 해 값.
   *
   * @param state IN_EFFECT 오늘 판정에 쓰는 값 · SCHEDULED 쓰기 시작하는 날이 아직 안 옴(예약) · PAST 지난 해
   * @param updatedBy 마지막으로 바꾼 관리자 (로그인 계정 ID, 마이그레이션으로 넣은 값이면 null)
   */
  public record Year(
      int year,
      LocalDate validFrom,
      String state,
      JsonNode data,
      String source,
      String updatedBy,
      OffsetDateTime updatedAt) {}

  /** 바꾼 기록 한 줄: 바뀌기 전 값과 바뀐 때·바꾼 사람. */
  public record Change(
      int year,
      LocalDate validFrom,
      JsonNode before,
      String source,
      OffsetDateTime replacedAt,
      String replacedBy) {}

  /** 바꾼 기록 (최근 것부터). */
  public record Changes(String kind, List<Change> changes) {}
}
