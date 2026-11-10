package kr.mujuthaek.api.area.domain;

import static kr.mujuthaek.api.area.domain.AreaMetric.CLINIC_COUNT_500M;
import static kr.mujuthaek.api.area.domain.AreaMetric.CONVENIENCE_STORE_COUNT_300M;
import static kr.mujuthaek.api.area.domain.AreaMetric.ELEMENTARY_NEAREST_M;
import static kr.mujuthaek.api.area.domain.AreaMetric.HIGH_COUNT_1KM;
import static kr.mujuthaek.api.area.domain.AreaMetric.MIDDLE_COUNT_1KM;
import static kr.mujuthaek.api.area.domain.AreaMetric.PARK_NEAREST_M;
import static kr.mujuthaek.api.area.domain.AreaMetric.STATION_NEAREST_M;

import java.math.BigDecimal;
import java.util.EnumSet;
import java.util.Map;
import java.util.Set;
import java.util.function.Predicate;

/**
 * 세권 태그. 저장하지 않고 조회 때 지표로 정해요. 코드는 API 문서의 {@code tags} 값과 같아요.
 *
 * <p>지표가 없으면(근처에 그 시설이 아예 없음) 거리는 무한히 멀고 수는 0으로 봐요.
 */
public enum AreaTag {
  /** 역세권: 역 500m 이내 */
  STATION(m -> atMost(m, STATION_NEAREST_M, 500)),
  /** 학세권: 초등학교 1km 이내이고 1km 안 중·고등학교 2곳 이상 */
  SCHOOL(
      m ->
          atMost(m, ELEMENTARY_NEAREST_M, 1000)
              && count(m, MIDDLE_COUNT_1KM) + count(m, HIGH_COUNT_1KM) >= 2),
  /** 초품아: 초등학교 300m 이내 */
  ELEMENTARY_NEAR(m -> atMost(m, ELEMENTARY_NEAREST_M, 300)),
  /** 숲·공세권: 공원 500m 이내 */
  PARK(m -> atMost(m, PARK_NEAREST_M, 500)),
  /** 편세권: 300m 안 편의점 3곳 이상 */
  CONVENIENCE(m -> count(m, CONVENIENCE_STORE_COUNT_300M) >= 3),
  /** 의세권: 500m 안 동네 의원 3곳 이상 */
  CLINIC(m -> count(m, CLINIC_COUNT_500M) >= 3);

  private final Predicate<Map<AreaMetric, BigDecimal>> rule;

  AreaTag(Predicate<Map<AreaMetric, BigDecimal>> rule) {
    this.rule = rule;
  }

  public static Set<AreaTag> of(Map<AreaMetric, BigDecimal> metrics) {
    Set<AreaTag> tags = EnumSet.noneOf(AreaTag.class);
    for (AreaTag tag : values()) {
      if (tag.rule.test(metrics)) {
        tags.add(tag);
      }
    }
    return tags;
  }

  private static boolean atMost(Map<AreaMetric, BigDecimal> m, AreaMetric metric, int meters) {
    BigDecimal v = m.get(metric);
    return v != null && v.compareTo(BigDecimal.valueOf(meters)) <= 0;
  }

  private static int count(Map<AreaMetric, BigDecimal> m, AreaMetric metric) {
    BigDecimal v = m.get(metric);
    return v == null ? 0 : v.intValue();
  }
}
