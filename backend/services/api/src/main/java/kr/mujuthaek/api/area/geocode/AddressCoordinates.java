package kr.mujuthaek.api.area.geocode;

/** 검색 API가 찾은 건물의 출입구 좌표 (도로명주소 좌표제공 API, {@link JusoCoordClient}). 테스트에서는 가짜로 바꿔 넣어요. */
public interface AddressCoordinates {

  /** 검색 결과 한 줄(법정동코드·도로명코드·지하 여부·건물번호)로 좌표를 받아요. 실패해도 예외 대신 {@link CoordOutcome}. */
  CoordOutcome coordinates(JusoResult building);
}
