package kr.mujuthaek.api.eligibility.rule;

/**
 * 소득 기준 금액 (기준 중위소득·도시근로자 월평균소득의 가구원 수별 월액). 연도마다 달라서 판정 엔진 밖(기준값 테이블)에서 받아요.
 *
 * <p>공고에 인쇄된 상한표가 있으면 그걸 먼저 쓰고, 없을 때만 이 값 × 비율로 상한을 계산해요.
 */
@FunctionalInterface
public interface IncomeBenchmarks {

  /** 모르면 null. */
  Long monthlyWon(String standard, int year, int householdSize);

  IncomeBenchmarks NONE = (standard, year, householdSize) -> null;
}
