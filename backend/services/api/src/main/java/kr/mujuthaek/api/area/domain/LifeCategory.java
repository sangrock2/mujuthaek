package kr.mujuthaek.api.area.domain;

/**
 * 생활권 총점의 항목. 앞의 5개는 저장된 항목 점수(area.location_scores.category), {@link #WORK}는 요청 때 통근 거리로 매겨요. 코드는
 * API 문서의 {@code priorities}·{@code categoryScores} 키와 같아요.
 */
public enum LifeCategory {
  TRANSIT,
  SCHOOL,
  PARK,
  CONVENIENCE,
  HOSPITAL,
  WORK
}
