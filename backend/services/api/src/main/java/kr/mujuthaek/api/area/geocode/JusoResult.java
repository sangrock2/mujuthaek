package kr.mujuthaek.api.area.geocode;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

/**
 * 검색 API 결과 한 줄({@code results.juso[]}). 칸 이름은 API 그대로예요. 값은 모두 문자열로 와요.
 *
 * @param admCd 행정구역코드 = 법정동코드 10자리
 * @param rn 도로명
 * @param udrtYn 지하 여부 0 지상, 1 지하
 * @param buldMnnm 건물 본번
 * @param buldSlno 건물 부번 (없으면 0)
 * @param rnMgtSn 도로명코드 12자리
 * @param bdMgtSn 건물관리번호
 */
@JsonIgnoreProperties(ignoreUnknown = true)
public record JusoResult(
    String admCd,
    String rn,
    String udrtYn,
    String buldMnnm,
    String buldSlno,
    String rnMgtSn,
    String bdMgtSn,
    String siNm,
    String sggNm,
    String emdNm,
    String jibunAddr,
    String roadAddr) {

  /** 법정동코드 앞 5자리 = 시군구 코드. 주소 사전(address_points.sigungu_code)과 같은 값이에요. */
  public String sigunguCode() {
    return admCd == null || admCd.length() < 5 ? null : admCd.substring(0, 5);
  }

  public boolean underground() {
    return "1".equals(udrtYn);
  }

  public int buildingMain() {
    return number(buldMnnm);
  }

  public int buildingSub() {
    return number(buldSlno);
  }

  /** 주소 사전에서 같은 출입구를 가리키는지 볼 때 쓰는 열쇠: 시군구·도로명·지하·본번·부번. */
  String roadKey() {
    return sigunguCode() + '|' + rn + '|' + udrtYn + '|' + buildingMain() + '-' + buildingSub();
  }

  private static int number(String v) {
    return v == null || v.isBlank() ? 0 : Integer.parseInt(v.trim());
  }
}
