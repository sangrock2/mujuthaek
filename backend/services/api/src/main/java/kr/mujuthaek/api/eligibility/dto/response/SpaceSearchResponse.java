package kr.mujuthaek.api.eligibility.dto.response;

import java.time.LocalDate;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import kr.mujuthaek.api.eligibility.model.MissingInput;
import kr.mujuthaek.api.eligibility.rule.Eligibility;

/**
 * 사업공간 맞춤 목록 (POST /spaces/search). counts는 지원 불가를 빼기 전, 종류·지역 필터를 건 개수예요. typeCounts는 지역 필터만 건 종류별
 * 개수예요 (종류 칩에 써요).
 */
public record SpaceSearchResponse(
    Counts counts,
    Map<String, Integer> typeCounts,
    List<Item> items,
    String nextCursor,
    boolean hasNext) {

  public record Counts(int eligible, int needsInput, int ineligible) {}

  /**
   * @param policy 사업공간 모집 정책(K-Startup·기업마당 입주기업 모집)이면 true. 공고 상세(GET /notices/{id})로 찾을 수 없어서 화면은
   *     detailUrl 원문으로 보내요
   * @param source 모집 정책의 출처 KSTARTUP · BIZINFO (원문 주소로 정해요). 공고·모르면 null
   * @param spaceType STARTUP_SPACE · SHOP_RENTAL · MEETING_ROOM. 모집 정책은 입주기업 모집이라 STARTUP_SPACE
   * @param provider 공고 기관 코드 (모집 정책은 null)
   * @param organization 모집 정책의 운영 기관 이름 (출처 칸, 공고·모르면 null)
   * @param regionCodes 공고 지역 법정동코드 10자리 (판정 목록과 같아요). 전국은 빈 목록, 모르면 null
   * @param status UPCOMING · APPLYING · ALWAYS
   * @param reason 판정 틀이 아직 없어 확인 필요면 CONDITIONS_NOT_READY
   * @param groups 지원 가능이면 충족한 대상, 확인 필요면 될 수도 있는 대상
   * @param missingInputs 확인 필요일 때 넣으면 결과가 정해질 수 있는 입력
   */
  public record Item(
      UUID id,
      boolean policy,
      String source,
      String spaceType,
      String title,
      String provider,
      String organization,
      String regionName,
      List<String> regionCodes,
      String status,
      LocalDate applyStart,
      LocalDate applyEnd,
      Integer dday,
      Eligibility overall,
      String reason,
      List<String> groups,
      List<MissingInput> missingInputs,
      String detailUrl,
      List<String> tags,
      String applyNote) {}
}
