package kr.mujuthaek.api.area.geocode;

import java.util.List;

/** 검색 API 한 번 부른 결과. */
public sealed interface SearchOutcome {

  /** 결과가 하나 이상. */
  record Found(List<JusoResult> results, int totalCount) implements SearchOutcome {
    public Found {
      results = List.copyOf(results);
    }
  }

  /** 정상 응답인데 결과 0개. */
  record NotFound() implements SearchOutcome {}

  /**
   * 검색어 문제로 API가 거절함(E0005~E0013, E0015: 너무 짧음·너무 김·범위 초과 등). 같은 검색어로 다시 불러도 같아서 재시도하지 않아요. 좌표 찾기에선
   * NOT_FOUND와 같게 다뤄요.
   */
  record Rejected(String errorCode) implements SearchOutcome {}

  /** API를 쓸 수 없음 — 좌표 찾기에선 API_ERROR. */
  record Failed(Reason reason, String errorCode) implements SearchOutcome {}

  enum Reason {
    /** 승인키가 설정되지 않음 (부르지 않음) */
    NO_KEY,
    /** 승인키 오류·만료 (E0001, E0014) */
    KEY_REJECTED,
    /** 하루 호출 수를 넘음 (부르지 않음) */
    RATE_LIMITED,
    /** 시스템 오류(-999)·HTTP 오류·연결 실패가 재시도 뒤에도 계속됨 */
    UNAVAILABLE
  }
}
