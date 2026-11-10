package kr.mujuthaek.api.area.geocode;

/** 주소 검색 (도로명주소 검색 API, {@link JusoSearchClient}). 좌표 찾기 테스트에서는 가짜 검색으로 바꿔 넣어요. */
public interface AddressSearch {

  /** 검색어로 첫 쪽을 받아요. 실패해도 예외 대신 {@link SearchOutcome}로 돌려줘요. */
  SearchOutcome search(String keyword);
}
