package kr.mujuthaek.api.area.domain;

/**
 * 찾은 좌표가 주소의 행정구역 안에 있는지 (좌표 찾기 3단계의 마지막 검사).
 *
 * @param sigungu 시군구 경계 검사 결과. {@link Sigungu#OUT_OF_REGION}이면 그 좌표는 버려요(FAILED·OUT_OF_REGION)
 * @param emdMismatch 받은 법정동의 경계 밖이면 true. 실패가 아니라 표시만 해요(region_mismatch) — 법정동은 공고 쪽 값이 틀리는 경우가
 *     있어서요
 */
public record BoundaryCheck(Sigungu sigungu, boolean emdMismatch) {

  /** 경계에서 이만큼 밖까지는 안으로 봐요. 건물 출입구가 경계를 몇 m 넘는 경우를 실패로 만들지 않으려고. */
  public static final int TOLERANCE_METERS = 50;

  public enum Sigungu {
    /** 경계 안 또는 50m 이내 */
    INSIDE,
    /** 경계에서 50m 넘게 밖 */
    OUT_OF_REGION,
    /** 그 시군구 경계 자료가 없음(경계를 아직 적재하지 않은 환경 등) — 검사하지 못해서 통과로 봐요 */
    NO_BOUNDARY
  }

  public boolean passed() {
    return sigungu != Sigungu.OUT_OF_REGION;
  }
}
