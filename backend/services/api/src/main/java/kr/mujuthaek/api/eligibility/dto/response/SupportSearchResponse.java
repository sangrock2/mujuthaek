package kr.mujuthaek.api.eligibility.dto.response;

import java.time.LocalDate;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import kr.mujuthaek.api.eligibility.model.MissingInput;
import kr.mujuthaek.api.eligibility.rule.Eligibility;

/**
 * 사업 지원 맞춤 목록 (POST /supports/search). counts는 지원 불가를 빼기 전, 종류·지역 필터를 건 개수예요. subFieldCounts는 지역
 * 필터만 건 종류별 개수예요 (종류 칩에 써요).
 */
public record SupportSearchResponse(
    Counts counts,
    Map<String, Integer> subFieldCounts,
    List<Item> items,
    String nextCursor,
    boolean hasNext) {

  public record Counts(int eligible, int needsInput, int ineligible) {}

  /**
   * @param source 출처 KSTARTUP · BIZINFO (원문 주소로 정해요). 모르면 null
   * @param subField FUND(지원금) · LOAN(정책자금) · TAX(세금 감면). 출처의 지원 분야로, 없으면 이름으로 정해요
   * @param supportArea 출처가 붙인 지원 분야 (예: 사업화 · 융자 · 시설ㆍ공간ㆍ보육). 모르면 null
   * @param organization 공고·운영 기관 (출처 칸). 모르면 null
   * @param amountText 요약 글의 「최대 · 한도 N원」 구절. 없으면 null
   * @param regionCodes 사업 지역 법정동코드 10자리. 전국은 빈 목록, 모르면 null
   * @param status UPCOMING · APPLYING · ALWAYS (기간으로 정해요)
   * @param reason 판정 틀이 아직 없어 확인 필요면 CONDITIONS_NOT_READY
   * @param missingInputs 확인 필요일 때 넣으면 결과가 정해질 수 있는 입력
   */
  public record Item(
      UUID id,
      String source,
      String subField,
      String supportArea,
      String organization,
      String amountText,
      String title,
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
      String applyNote) {}
}
