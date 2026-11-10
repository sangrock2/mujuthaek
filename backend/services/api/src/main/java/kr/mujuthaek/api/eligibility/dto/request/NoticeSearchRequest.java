package kr.mujuthaek.api.eligibility.dto.request;

import io.swagger.v3.oas.annotations.media.ArraySchema;
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import java.util.List;

/**
 * 맞춤 목록 요청 (POST /notices/search). 판정 입력이 섞여서 GET이 아니라 POST예요.
 *
 * @param sort RECOMMENDED(기본: 지원 가능 → 확인 필요 → 마감 임박 → 생활권 총점) · DEADLINE · PREPARE_COST(준비할 돈 적은 순)
 *     · AREA_SCORE(생활권 총점 높은 순)
 * @param includeIneligible 지원 불가 공고도 보여줄지 (기본 false)
 */
public record NoticeSearchRequest(
    @Valid Filters filters,
    @Valid ApplicantRequest applicant,
    @Schema(defaultValue = "RECOMMENDED")
        @Pattern(regexp = "RECOMMENDED|DEADLINE|PREPARE_COST|AREA_SCORE")
        String sort,
    @Schema(defaultValue = "false") Boolean includeIneligible,
    String cursor,
    @Schema(defaultValue = "20") @Min(1) @Max(100) Integer size) {

  /**
   * 공개 목록(GET /notices)과 같은 필터. statuses를 비우면 접수예정·접수중이에요.
   *
   * @param keyword 검색어. 띄어쓰기로 나눈 낱말이 모두 제목에 들어 있는 공고만. 비우면 전부
   */
  public record Filters(
      @Schema(
              allowableValues = {"HOUSING", "BUSINESS_SPACE"},
              defaultValue = "HOUSING")
          String field,
      @ArraySchema(schema = @Schema(pattern = "^[0-9]{2}([0-9]{3})?$", example = "11680"))
          List<String> regionCodes,
      @Schema(allowableValues = {"RENT", "BUY"}) String tenure,
      @ArraySchema(
              schema =
                  @Schema(
                      allowableValues = {
                        "YOUTH_SAFE_HOUSING",
                        "PUBLIC_SUPPORT_PRIVATE_RENTAL",
                        "INTEGRATED_PUBLIC_RENTAL",
                        "PUBLIC_RENTAL",
                        "HAPPY_HOUSING",
                        "NATIONAL_RENTAL",
                        "PERMANENT_RENTAL",
                        "PURCHASE_RENTAL",
                        "JEONSE_RENTAL",
                        "LONG_TERM_JEONSE",
                        "PUBLIC_SALE",
                        "PRIVATE_SALE",
                        "STARTUP_SPACE",
                        "SHOP_RENTAL",
                        "MEETING_ROOM"
                      }))
          List<String> noticeTypes,
      List<String> providers,
      @ArraySchema(
              arraySchema = @Schema(description = "비우면 UPCOMING · APPLYING · ALWAYS · UNKNOWN"),
              schema =
                  @Schema(
                      allowableValues = {"UPCOMING", "APPLYING", "CLOSED", "ALWAYS", "UNKNOWN"}))
          List<String> statuses,
      @Size(max = 100) String keyword) {}

  public Filters filtersOrEmpty() {
    return filters == null ? new Filters(null, null, null, null, null, null, null) : filters;
  }

  public String sortOrDefault() {
    return sort == null ? "RECOMMENDED" : sort;
  }
}
