package kr.mujuthaek.api.area.domain;

import java.util.Locale;

/**
 * 위치마다 저장하는 세권 지표 14개. area.location_metrics.metric 값은 {@link #code()}(소문자 이름)예요.
 *
 * <p>거리는 미터(직선), 수는 반경 안 개수예요. 근처에 그 시설이 아예 없으면 지표를 저장하지 않아요(점수에서 0점).
 */
public enum AreaMetric {
  STATION_NEAREST_M,
  /** 역 이름으로 묶어 셈 — 환승역 하나 = 1 */
  STATION_COUNT_1KM,
  BUS_STOP_NEAREST_M,
  BUS_STOP_COUNT_300M,
  ELEMENTARY_NEAREST_M,
  MIDDLE_COUNT_1KM,
  HIGH_COUNT_1KM,
  PARK_NEAREST_M,
  PARK_AREA_1KM_M2,
  /** 2차 이상 병원 */
  HOSPITAL_NEAREST_M,
  /** 동네 의원 */
  CLINIC_COUNT_500M,
  CONVENIENCE_STORE_COUNT_300M,
  /** 슈퍼마켓 */
  MART_NEAREST_M,
  STORE_COUNT_300M;

  public String code() {
    return name().toLowerCase(Locale.ROOT);
  }

  public static AreaMetric ofCode(String code) {
    return valueOf(code.toUpperCase(Locale.ROOT));
  }
}
