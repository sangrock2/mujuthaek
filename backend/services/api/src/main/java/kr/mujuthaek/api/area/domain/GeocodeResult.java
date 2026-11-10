package kr.mujuthaek.api.area.domain;

/**
 * 공고 주소 하나를 좌표로 바꾼 결과. 값은 area.notice_locations의 status·method·fail_reason·bjd_code_found와 같아요(저장은
 * 3-5).
 *
 * @param coordinate FAILED면 null
 * @param bjdCodeFound 찾은 좌표의 법정동코드 (사전 주소의 법정동, 중심점이면 그 법정동). FAILED면 null
 * @param sigunguCode 찾는 데 쓴 시군구 코드 5자리 (받은 법정동코드 또는 주소 이름에서). 경계 검사에 써요. 모르면 null
 * @param addressId 사전 주소의 도로명주소관리번호 (OK일 때만)
 * @param failReason FAILED일 때만
 * @param regionMismatch 받은 법정동의 경계 밖 (실패가 아니라 표시만, notice_locations.region_mismatch)
 */
public record GeocodeResult(
    Status status,
    Method method,
    Coordinate coordinate,
    String bjdCodeFound,
    String sigunguCode,
    String addressId,
    FailReason failReason,
    boolean regionMismatch) {

  public enum Status {
    /** 사전 주소의 출입구 좌표 */
    OK,
    /** 법정동 대표점 (대략 위치) */
    APPROX,
    FAILED
  }

  public enum Method {
    /** 사전에서 받은 도로명 그대로 */
    FILE,
    /** 사전에서 도로명 글자 하나 오타를 고쳐서 */
    FUZZY,
    /** 검색 API로 찾은 도로명·번호로 사전에서 */
    SEARCH_API,
    /** 사전에 없는 새 건물: 검색 API로 찾은 건물의 좌표제공 API 출입구 좌표 */
    COORD_API,
    /** 법정동 대표점 */
    CENTROID
  }

  public enum FailReason {
    /** 사전·검색 API·대표점 모두 없음 */
    NOT_FOUND,
    /** 주소에서 지역도 번호도 못 읽음 */
    PARSE_FAILED,
    /** 검색 API를 쓸 수 없었고(한도·장애·키 오류) 대표점도 없음 — 나중에 다시 하면 찾을 수 있어요 */
    API_ERROR,
    /** 찾은 좌표가 주소의 시군구 경계에서 50m 넘게 밖 (사전 좌표 오류·검색 결과가 다른 시군구 등) — 좌표를 버려요 */
    OUT_OF_REGION
  }

  static GeocodeResult ok(Method method, AddressMatch match, String sigunguCode) {
    return new GeocodeResult(
        Status.OK,
        method,
        new Coordinate(match.lat(), match.lng()),
        match.bjdCode(),
        sigunguCode,
        match.addressId(),
        null,
        false);
  }

  public static GeocodeResult ok(AddressMatch match, String sigunguCode) {
    return ok(
        match.method() == AddressMatch.Method.FUZZY ? Method.FUZZY : Method.FILE,
        match,
        sigunguCode);
  }

  public static GeocodeResult bySearch(AddressMatch match, String sigunguCode) {
    return ok(Method.SEARCH_API, match, sigunguCode);
  }

  /** 사전에 없는 새 건물을 좌표제공 API로 (주소 ID는 사전 것이 아니라 없어요). */
  public static GeocodeResult byCoordApi(Coordinate point, String bjdCode, String sigunguCode) {
    return new GeocodeResult(
        Status.OK, Method.COORD_API, point, bjdCode, sigunguCode, null, null, false);
  }

  public static GeocodeResult approx(Coordinate point, String bjdCode, String sigunguCode) {
    return new GeocodeResult(
        Status.APPROX, Method.CENTROID, point, bjdCode, sigunguCode, null, null, false);
  }

  public static GeocodeResult failed(FailReason reason, String sigunguCode) {
    return new GeocodeResult(Status.FAILED, null, null, null, sigunguCode, null, reason, false);
  }

  /** 받은 법정동 경계 밖이라고 표시한 같은 결과. */
  public GeocodeResult withRegionMismatch() {
    return new GeocodeResult(
        status, method, coordinate, bjdCodeFound, sigunguCode, addressId, failReason, true);
  }
}
