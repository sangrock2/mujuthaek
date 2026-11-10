package kr.mujuthaek.api.area.domain;

import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;
import java.util.List;

/**
 * 생활권·상권 기초 데이터 원천. 원천마다 파일 인코딩, 꼭 있어야 하는 칸, 변환 SQL이 달라요.
 *
 * <p>칸 이름은 원천 파일 머리줄 그대로예요 (area 설계 1단계 표).
 */
public enum AreaSource {
  SUBWAY_STATION(
      Target.FACILITIES,
      "SUBWAY_STATION",
      StandardCharsets.UTF_8,
      List.of("역번호", "역사명", "노선번호", "노선명", "환승역구분", "역위도", "역경도", "운영기관명", "역사도로명주소"),
      "subway_station.sql"),
  BUS_STOP(
      Target.FACILITIES,
      "BUS_STOP",
      Charsets.CP949,
      List.of("정류장번호", "정류장명", "위도", "경도", "도시코드", "도시명"),
      "bus_stop.sql"),
  SCHOOL(
      Target.FACILITIES,
      "SCHOOL",
      Charsets.CP949,
      List.of("학교ID", "학교명", "학교급구분", "설립형태", "본교분교구분", "운영상태", "소재지지번주소", "소재지도로명주소", "위도", "경도"),
      "school.sql"),
  PARK(
      Target.FACILITIES,
      "PARK",
      Charsets.CP949,
      List.of("관리번호", "공원명", "공원구분", "소재지도로명주소", "소재지지번주소", "위도", "경도", "공원면적"),
      "park.sql"),
  HOSPITAL(
      Target.FACILITIES,
      "HOSPITAL",
      Charsets.CP949,
      List.of("암호화요양기호", "요양기관명", "종별코드", "종별코드명", "주소", "좌표(X)", "좌표(Y)"),
      "hospital.sql"),
  STORES(
      Target.STORES,
      null,
      StandardCharsets.UTF_8,
      List.of(
          "상가업소번호",
          "상호명",
          "지점명",
          "상권업종대분류코드",
          "상권업종대분류명",
          "상권업종중분류코드",
          "상권업종중분류명",
          "상권업종소분류코드",
          "상권업종소분류명",
          "도로명주소",
          "경도",
          "위도"),
      "stores.sql"),
  /** 도로명주소 출입구 정보: 머리줄 없는 | 구분 19칸이라 칸 이름은 c1~c19로 고정해요. 시도 코드 파일마다 적재해요. */
  ADDRESS_ENTRANCE(
      Target.ADDRESS_POINTS,
      null,
      Charsets.CP949,
      List.of(
          "c1", "c2", "c3", "c4", "c5", "c6", "c7", "c8", "c9", "c10", "c11", "c12", "c13", "c14",
          "c15", "c16", "c17", "c18", "c19"),
      "address_entrance.sql",
      '|',
      true),
  /** 시군구 경계: collector가 구역의 도형 SHP를 바꾼 전국 CSV(code, name, wkt — UTM-K). 좌표 찾기의 경계 검사에 써요. */
  REGION_BOUNDARY_SIG(
      Target.REGION_BOUNDARIES,
      null,
      StandardCharsets.UTF_8,
      List.of("code", "name", "wkt"),
      "region_boundary_sig.sql"),
  /** 법정읍면동 경계: 시군구와 같은 모양, 코드 8자리. */
  REGION_BOUNDARY_EMD(
      Target.REGION_BOUNDARIES,
      null,
      StandardCharsets.UTF_8,
      List.of("code", "name", "wkt"),
      "region_boundary_emd.sql");

  /** 적재되는 테이블. */
  public enum Target {
    FACILITIES,
    STORES,
    ADDRESS_POINTS,
    REGION_BOUNDARIES
  }

  private final Target target;
  private final String facilityKind;
  private final Charset charset;
  private final List<String> requiredColumns;
  private final String mappingSql;
  private final char delimiter;
  private final boolean headerless;

  AreaSource(
      Target target,
      String facilityKind,
      Charset charset,
      List<String> requiredColumns,
      String mappingSql) {
    this(target, facilityKind, charset, requiredColumns, mappingSql, ',', false);
  }

  AreaSource(
      Target target,
      String facilityKind,
      Charset charset,
      List<String> requiredColumns,
      String mappingSql,
      char delimiter,
      boolean headerless) {
    this.target = target;
    this.facilityKind = facilityKind;
    this.charset = charset;
    this.requiredColumns = requiredColumns;
    this.mappingSql = mappingSql;
    this.delimiter = delimiter;
    this.headerless = headerless;
  }

  public Target target() {
    return target;
  }

  /** facilities.kind 값. 상가정보는 null. */
  public String facilityKind() {
    return facilityKind;
  }

  public Charset charset() {
    return charset;
  }

  public List<String> requiredColumns() {
    return requiredColumns;
  }

  /** classpath area/load/ 아래 변환 SQL 파일 이름. */
  public String mappingSql() {
    return mappingSql;
  }

  /** area.region_boundaries.level 값 (SIG·EMD). 경계가 아닌 원천은 null. */
  public String boundaryLevel() {
    return switch (this) {
      case REGION_BOUNDARY_SIG -> "SIG";
      case REGION_BOUNDARY_EMD -> "EMD";
      default -> null;
    };
  }

  /** 칸 구분자. CSV는 쉼표. */
  public char delimiter() {
    return delimiter;
  }

  /** 머리줄이 없으면 true. 그때 칸 이름은 requiredColumns 순서 그대로예요. */
  public boolean headerless() {
    return headerless;
  }

  /** 시도 파일마다 따로 적재해서 scope(시도)가 꼭 필요한 원천. 지우기도 그 시도 안에서만 해요. */
  public boolean scoped() {
    return target == Target.STORES || target == Target.ADDRESS_POINTS;
  }

  /** 공공데이터 파일 대부분이 쓰는 한국어 윈도 인코딩. PostgreSQL COPY에서는 UHC라는 이름이에요. */
  public static final class Charsets {
    public static final Charset CP949 = Charset.forName("MS949");

    private Charsets() {}
  }
}
