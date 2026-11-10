package kr.mujuthaek.api.area.geocode;

import kr.mujuthaek.api.area.geocode.SearchOutcome.Reason;

/** 좌표제공 API 한 번 부른 결과. */
public sealed interface CoordOutcome {

  /** 건물 출입구 좌표 (UTM-K, EPSG:5179, 미터). */
  record Found(double entX, double entY) implements CoordOutcome {}

  /** 정상 응답인데 좌표 없음. */
  record NotFound() implements CoordOutcome {}

  /** 요청 값 문제로 API가 거절함 (다시 불러도 같아서 재시도 안 함). 좌표 찾기에선 NotFound와 같게 다뤄요. */
  record Rejected(String errorCode) implements CoordOutcome {}

  /** API를 쓸 수 없음 (키 없음·키 오류·한도·장애). 검색 API와 같은 이유 값을 써요. */
  record Failed(Reason reason, String errorCode) implements CoordOutcome {}
}
