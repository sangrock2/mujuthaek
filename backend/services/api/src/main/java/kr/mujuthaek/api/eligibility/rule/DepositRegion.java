package kr.mujuthaek.api.eligibility.rule;

import java.time.LocalDate;
import java.util.Optional;
import java.util.Set;

/** 청약 예치기준금액의 지역 구분 (주택공급에 관한 규칙 별표 2의 세 열). 지역은 입주자모집공고일 현재 신청자의 주민등록 거주지예요 (별표 2 비고). */
public enum DepositRegion {
  /** 특별시 및 부산광역시. */
  SEOUL_BUSAN,
  /** 그 밖의 광역시. */
  METROPOLITAN,
  /** 특별시 및 광역시를 제외한 지역. 세종특별자치시·특별자치도도 별표에 따로 적혀 있지 않아 글자대로 여기로 봐요. */
  OTHER;

  /**
   * 전남광주통합특별시 출범일. 별표 2(2023. 5. 10. 개정판)가 통합특별시를 어느 열로 볼지 정하지 않아서, 이날부터 광주·전남 거주자는 열을 정하지 않아요 (판정은
   * 확인 필요).
   */
  public static final LocalDate GWANGJU_JEONNAM_MERGED = LocalDate.of(2026, 7, 1);

  /** 대구 27, 인천 28, 대전 30, 울산 31. 광주 29는 통합 전까지만. */
  private static final Set<String> METROPOLITAN_SIDO = Set.of("27", "28", "30", "31");

  /** 세종 36, 경기 41, 강원 42·51, 충북 43, 충남 44, 전북 45·52, 경북 47, 경남 48, 제주 50. 전남 46은 통합 전까지만. */
  private static final Set<String> OTHER_SIDO =
      Set.of("36", "41", "42", "43", "44", "45", "47", "48", "50", "51", "52");

  /** 거주지 법정동코드(2자리 이상)의 시도 두 자리로 골라요. 모르는 시도이거나 열을 정할 수 없으면 비어 있어요. */
  public static Optional<DepositRegion> of(String regionCode, LocalDate day) {
    String sido = regionCode.substring(0, 2);
    boolean merged = !day.isBefore(GWANGJU_JEONNAM_MERGED);
    if (sido.equals("11") || sido.equals("26")) {
      return Optional.of(SEOUL_BUSAN);
    }
    if (METROPOLITAN_SIDO.contains(sido) || (sido.equals("29") && !merged)) {
      return Optional.of(METROPOLITAN);
    }
    if (OTHER_SIDO.contains(sido) || (sido.equals("46") && !merged)) {
      return Optional.of(OTHER);
    }
    return Optional.empty();
  }
}
