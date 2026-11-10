package kr.mujuthaek.api.area.domain;

/**
 * 도로명주소 사전(area.address_points)에서 찾은 주소 하나.
 *
 * @param addressId 도로명주소관리번호 26자리
 * @param bjdCode 법정동코드 10자리
 * @param roadName 사전의 도로명 (오타로 찾았으면 받은 이름이 아니라 고친 이름)
 * @param method 찾은 방법 (area.notice_locations.method와 같은 값)
 */
public record AddressMatch(
    String addressId,
    String bjdCode,
    String roadName,
    int underground,
    int bldgMain,
    int bldgSub,
    double lat,
    double lng,
    Method method) {

  public enum Method {
    /** 받은 도로명(띄어쓰기만 지움)과 번호가 그대로 맞음 */
    FILE,
    /** 도로명 오타를 같은 시군구의 비슷한 도로명으로 고쳐서 찾음 (후보 중 하나만 맞을 때만) */
    FUZZY
  }
}
