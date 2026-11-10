package kr.mujuthaek.api.area.domain;

import java.math.BigDecimal;
import java.util.List;

/**
 * 생활권·상권 점수 기준표와 데이터 출처 (GET /areas/criteria). 화면이 "역 500m 안 100점" 같은 기준과 생활권 화면 아래 출처를 보여요.
 *
 * @param scoreVersion 쓰는 규칙 버전
 * @param rules 지표별 구간: xs(거리 m·개수·입지계수) → ys(점수), 사이는 직선, 양끝 밖은 끝 값
 * @param weights 생활권 항목(TRANSIT 등)을 이루는 지표와 그 비중
 * @param sources 데이터 출처 (병원은 공공누리 제1유형이라 링크 표기 필수)
 */
public record AreaCriteria(
    String scoreVersion, List<Rule> rules, List<Weight> weights, List<Source> sources) {

  public record Rule(String metric, List<BigDecimal> xs, List<BigDecimal> ys) {}

  public record Weight(String category, String metric, BigDecimal weight) {}

  /**
   * @param license 이용 조건 (모르면 null — 확인 전)
   * @param licenseUrl 이용 조건 안내 주소 (표기에 링크가 필요한 경우)
   */
  public record Source(String data, String provider, String license, String licenseUrl) {}

  /** 원천 파일 이름에서 알 수 있는 데이터·기관. 이용 조건은 병원만 확인됨(공공누리 제1유형). */
  public static final List<Source> SOURCES =
      List.of(
          new Source("전국 도시철도역", null, null, null),
          new Source("전국 버스정류장 위치정보", "국토교통부", null, null),
          new Source("전국초중등학교위치표준데이터", "공공데이터포털", null, null),
          new Source("전국도시공원정보표준데이터", "공공데이터포털", null, null),
          new Source(
              "병원정보서비스",
              "건강보험심사평가원",
              "공공누리 제1유형 (출처표시)",
              "https://www.kogl.or.kr/info/licenseType1.do"),
          new Source("상가(상권)정보", "소상공인시장진흥공단", null, null),
          new Source("도로명주소 출입구 정보·구역의 도형", "행정안전부 주소기반산업지원서비스", null, null));
}
