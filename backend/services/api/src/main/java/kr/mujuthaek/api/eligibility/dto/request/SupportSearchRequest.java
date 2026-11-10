package kr.mujuthaek.api.eligibility.dto.request;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import java.util.List;

/**
 * 사업 지원(창업지원 사업) 맞춤 목록 요청 (POST /supports/search). 판정 입력이 섞여서 POST예요. 공고마다 묻는 예/아니요 답은 받지 않아요
 * (2026-10-29 결정).
 *
 * @param applicant 판정 입력 (사업 입력은 business). 비우면 모든 사업이 확인 필요예요
 * @param sort RECOMMENDED(기본: 지원 가능 → 확인 필요 → 지원 불가, 같으면 마감 임박) · DEADLINE(마감 임박)
 * @param includeIneligible 지원 불가 사업도 보여줄지 (기본 false)
 */
public record SupportSearchRequest(
    @Valid Filters filters,
    @Valid JudgmentApplicantRequest applicant,
    @Schema(defaultValue = "RECOMMENDED") @Pattern(regexp = "RECOMMENDED|DEADLINE") String sort,
    @Schema(defaultValue = "false") Boolean includeIneligible,
    String cursor,
    @Schema(defaultValue = "20") @Min(1) @Max(100) Integer size) {

  /**
   * @param subFields FUND(지원금) · LOAN(정책자금) · TAX(세금 감면). 비우면 전부
   * @param regionCodes 시도 2자리 또는 시군구 5자리. 비우면 전국. 전국 사업과 지역을 모르는 사업은 늘 들어가요
   * @param keyword 검색어. 띄어쓰기로 나눈 낱말이 모두 이름(제목)·기관에 들어 있는 것만. 비우면 전부
   */
  public record Filters(
      List<@Pattern(regexp = "FUND|LOAN|TAX") String> subFields,
      List<@Pattern(regexp = "\\d{2}|\\d{5}") String> regionCodes,
      @Size(max = 100) String keyword) {}

  public Filters filtersOrEmpty() {
    return filters == null ? new Filters(null, null, null) : filters;
  }

  public String sortOrDefault() {
    return sort == null ? "RECOMMENDED" : sort;
  }
}
