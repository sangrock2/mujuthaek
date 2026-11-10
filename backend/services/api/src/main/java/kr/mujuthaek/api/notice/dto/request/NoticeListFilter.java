package kr.mujuthaek.api.notice.dto.request;

import java.time.LocalDate;
import java.util.List;
import kr.mujuthaek.api.common.exception.CustomException;
import kr.mujuthaek.api.common.exception.ErrorCode;
import kr.mujuthaek.api.common.text.Keywords;
import kr.mujuthaek.api.notice.domain.NoticeStatus;
import kr.mujuthaek.api.notice.domain.NoticeType;

/**
 * 공고 목록 필터 (GET /notices 쿼리). 목록 값은 쉼표로 이어도 되고 같은 이름을 여러 번 줘도 돼요.
 *
 * @param field HOUSING(기본) · BUSINESS_SPACE
 * @param regionCodes 시군구 5자리 또는 시도 2자리. 시도 단위 5자리(xx000, 예: 11000 = 서울특별시)는 시도 2자리와 같아서 그 시도의 모든
 *     시군구 공고가 나와요
 * @param tenure RENT 빌려서 · BUY 사서 (공고 유형에서 정해요: 공공·민영 분양이 BUY, 나머지는 유형을 못 정한 공고까지 RENT)
 * @param statuses 비우면 마감(CLOSED)을 뺀 전부 (확인 필요 UNKNOWN 포함)
 * @param sort DEADLINE(기본) 마감 임박 · LATEST 최신
 * @param applyEndFrom 마감일이 이날 이후(이날 포함)인 공고만. 마감일을 모르는 공고는 빠져요
 * @param applyEndTo 마감일이 이날 이전(이날 포함)인 공고만. 마감일을 모르는 공고는 빠져요
 * @param keyword 검색어. 낱말이 모두 제목에 들어 있는 공고만 ({@link Keywords}). 비우면 전부
 */
public record NoticeListFilter(
    String field,
    List<String> regionCodes,
    String tenure,
    List<String> noticeTypes,
    List<String> providers,
    List<String> statuses,
    String sort,
    LocalDate applyEndFrom,
    LocalDate applyEndTo,
    String keyword) {

  public static final List<String> BUY_TYPES =
      List.of(NoticeType.PUBLIC_SALE.name(), NoticeType.PRIVATE_SALE.name());

  public NoticeListFilter {
    field = field == null ? "HOUSING" : field;
    sort = sort == null ? "DEADLINE" : sort;
    regionCodes = regionCodes == null ? List.of() : regionCodes;
    noticeTypes = noticeTypes == null ? List.of() : noticeTypes;
    providers = providers == null ? List.of() : providers;
    statuses =
        statuses == null || statuses.isEmpty()
            ? List.of(
                NoticeStatus.UPCOMING.name(),
                NoticeStatus.APPLYING.name(),
                NoticeStatus.ALWAYS.name(),
                NoticeStatus.UNKNOWN.name())
            : statuses;
    check(List.of(field), List.of("HOUSING", "BUSINESS_SPACE"), "field");
    check(List.of(sort), List.of("DEADLINE", "LATEST"), "sort");
    check(tenure == null ? List.of() : List.of(tenure), List.of("RENT", "BUY"), "tenure");
    check(noticeTypes, names(NoticeType.values()), "noticeTypes");
    check(statuses, names(NoticeStatus.values()), "statuses");
    if (applyEndFrom != null && applyEndTo != null && applyEndFrom.isAfter(applyEndTo)) {
      throw invalid("applyEndFrom은 applyEndTo보다 늦을 수 없어요");
    }
    for (String code : regionCodes) {
      if (!code.matches("[0-9]{2}([0-9]{3})?")) {
        throw invalid("regionCodes는 시군구 5자리 또는 시도 2자리예요");
      }
    }
  }

  /** 검색어 없이 (공개 목록). */
  public NoticeListFilter(
      String field,
      List<String> regionCodes,
      String tenure,
      List<String> noticeTypes,
      List<String> providers,
      List<String> statuses,
      String sort,
      LocalDate applyEndFrom,
      LocalDate applyEndTo) {
    this(
        field,
        regionCodes,
        tenure,
        noticeTypes,
        providers,
        statuses,
        sort,
        applyEndFrom,
        applyEndTo,
        null);
  }

  /** 마감일 범위 없이 (다른 모듈의 후보 찾기 등). */
  public NoticeListFilter(
      String field,
      List<String> regionCodes,
      String tenure,
      List<String> noticeTypes,
      List<String> providers,
      List<String> statuses,
      String sort) {
    this(field, regionCodes, tenure, noticeTypes, providers, statuses, sort, null, null, null);
  }

  public Keywords keywords() {
    return Keywords.of(keyword);
  }

  /** 시군구 5자리 (시도 단위 xx000은 빼요). */
  public List<String> sigunguCodes() {
    return regionCodes.stream().filter(c -> c.length() == 5 && !c.endsWith("000")).toList();
  }

  /** 시도 2자리 (시도 단위 xx000은 앞 2자리로). */
  public List<String> sidoCodes() {
    return regionCodes.stream()
        .filter(c -> c.length() == 2 || c.endsWith("000"))
        .map(c -> c.substring(0, 2))
        .toList();
  }

  private static void check(List<String> values, List<String> allowed, String name) {
    for (String v : values) {
      if (!allowed.contains(v)) {
        throw invalid(name + "에 쓸 수 없는 값이에요 (가능: " + String.join(", ", allowed) + ")");
      }
    }
  }

  private static List<String> names(Enum<?>[] values) {
    return java.util.Arrays.stream(values).map(Enum::name).toList();
  }

  private static CustomException invalid(String detail) {
    return new CustomException(ErrorCode.VALIDATION_FAILED, detail);
  }
}
