package kr.mujuthaek.api.area.geocode;

import java.util.List;
import java.util.Optional;
import kr.mujuthaek.api.area.geocode.ParsedAddress.Kind;

/** 검색 답변 전체에서 공고 주소와 일치하는 출입구가 하나일 때만 선택해요. */
public final class JusoCandidates {
  private JusoCandidates() {}

  public static Optional<JusoResult> pick(
      SearchOutcome.Found found, ParsedAddress address, String bjd, String sigungu) {
    if (found.totalCount() != found.results().size()) {
      return Optional.empty();
    }
    List<JusoResult> matches =
        found.results().stream()
            .filter(r -> r.admCd() != null && r.admCd().matches("[0-9]{10}"))
            .filter(r -> sigungu == null || sigungu.equals(r.sigunguCode()))
            .filter(r -> matchesRegionCode(bjd, r))
            .filter(r -> sigungu != null || matchesRegionName(address, r))
            .filter(r -> matchesAddress(address, r))
            .toList();
    if (matches.isEmpty()) {
      return Optional.empty();
    }
    JusoResult first = matches.getFirst();
    return matches.stream().allMatch(r -> r.roadKey().equals(first.roadKey()))
        ? Optional.of(first)
        : Optional.empty();
  }

  private static boolean matchesRegionCode(String code, JusoResult result) {
    if (code == null) {
      return true;
    }
    // 행정구역 코드가 구 단위이면 뒤 다섯 자리의 0은 동을 지정하는 값이 아니에요.
    if (code.length() == 10 && code.endsWith("00000")) {
      return code.substring(0, 5).equals(result.sigunguCode());
    }
    return code.equals(result.admCd());
  }

  private static boolean matchesRegionName(ParsedAddress address, JusoResult result) {
    String sido = AddressNormalizer.SIDO.getOrDefault(result.siNm(), result.siNm());
    return (address.sido() == null || address.sido().equals(sido))
        && (address.sigungu() == null
            || compact(address.sigungu()).equals(compact(result.sggNm())));
  }

  private static boolean matchesAddress(ParsedAddress address, JusoResult result) {
    if (result.rn() == null
        || result.rn().isBlank()
        || !("0".equals(result.udrtYn()) || "1".equals(result.udrtYn()))) {
      return false;
    }
    try {
      if (result.buildingMain() <= 0 || result.buildingSub() < 0) {
        return false;
      }
      if (address.kind() == Kind.ROAD) {
        return compact(address.roadName()).equals(compact(result.rn()))
            && address.underground() == result.underground()
            && address.buildingMain() == result.buildingMain()
            && address.buildingSub() == result.buildingSub();
      }
      if (address.kind() == Kind.JIBUN) {
        ParsedAddress parcel = AddressParser.parse(result.jibunAddr());
        return parcel.kind() == Kind.JIBUN
            && compact(address.dong()).equals(compact(parcel.dong()))
            && address.mountain() == parcel.mountain()
            && address.jibunMain() == parcel.jibunMain()
            && address.jibunSub() == parcel.jibunSub();
      }
      return false;
    } catch (NumberFormatException invalidNumber) {
      return false;
    }
  }

  private static String compact(String value) {
    return value == null ? "" : value.replaceAll("\\s+", "");
  }
}
