package kr.mujuthaek.api.eligibility.rule;

import java.util.Map;
import java.util.OptionalLong;

/** 기준값 조회. 판정 코드는 이 인터페이스만 알고, 값은 service가 DB에서 읽어 줘요. */
public interface BaseValues {

  /**
   * 기준값 (원). 없으면 비어 있어요.
   *
   * @param program 자산 기준의 주택 유형 (예: 국민임대). 소득 기준은 빈 문자열
   * @param householdSize 소득 기준의 가구원 수. 자산 기준은 0
   */
  OptionalLong find(BaseValueKind kind, int year, String program, int householdSize);

  /**
   * 가구원 수별 표에서 금액 찾기. 표의 가장 큰 가구원 수보다 많으면 마지막 두 칸의 차이만큼 한 명마다 더해요 (기준 중위소득 고시의 8인 이상 계산 방식과 같아요).
   */
  static OptionalLong byHouseholdSize(Map<Integer, Long> table, int householdSize) {
    if (householdSize < 1 || table.isEmpty()) {
      return OptionalLong.empty();
    }
    Long exact = table.get(householdSize);
    if (exact != null) {
      return OptionalLong.of(exact);
    }
    int largest = table.keySet().stream().mapToInt(Integer::intValue).max().orElseThrow();
    Long last = table.get(largest);
    Long beforeLast = table.get(largest - 1);
    if (householdSize < largest || beforeLast == null) {
      return OptionalLong.empty();
    }
    return OptionalLong.of(last + (last - beforeLast) * (householdSize - largest));
  }
}
