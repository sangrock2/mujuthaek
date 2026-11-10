package kr.mujuthaek.api.area.geocode;

/**
 * 공고 주소를 나눈 결과. 시도·시군구는 글자 그대로(코드는 지역 코드표에서 찾아요).
 *
 * @param kind 도로명·지번·범위만·알 수 없음
 * @param sido 정식 시도 이름 (원문에 없으면 null)
 * @param sigungu 시군구 이름, 일반구가 있으면 "수원시 영통구"처럼 같이 (원문에 없으면 null)
 * @param roadName ROAD일 때 도로명 (띄어쓰기 없이, 예: 남부순환로180길)
 * @param underground ROAD일 때 지하 건물인지
 * @param buildingMain ROAD일 때 건물 본번
 * @param buildingSub ROAD일 때 건물 부번 (없으면 0)
 * @param dong JIBUN일 때 법정동·리 (리는 읍면까지, 예: 낭산면 용기리). ROAD면 괄호 안 동 이름(없으면 null)
 * @param mountain JIBUN일 때 산 번지인지
 * @param jibunMain JIBUN일 때 지번 본번
 * @param jibunSub JIBUN일 때 지번 부번 (없으면 0)
 * @param normalized 정리한 주소 글자
 */
public record ParsedAddress(
    Kind kind,
    String sido,
    String sigungu,
    String roadName,
    boolean underground,
    int buildingMain,
    int buildingSub,
    String dong,
    boolean mountain,
    int jibunMain,
    int jibunSub,
    String normalized) {

  public enum Kind {
    /** 도로명 + 건물번호 */
    ROAD,
    /** 법정동·리 + 지번 */
    JIBUN,
    /** 지역은 있지만 번호가 없음 (예: ○○지구 A17블록, ○○구 일대) */
    AREA_ONLY,
    /** 지역도 번호도 못 찾음 */
    UNKNOWN
  }
}
