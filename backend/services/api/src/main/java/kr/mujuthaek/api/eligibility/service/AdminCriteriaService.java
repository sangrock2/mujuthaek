package kr.mujuthaek.api.eligibility.service;

import java.time.Clock;
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.List;
import java.util.Set;
import java.util.UUID;
import java.util.stream.Stream;
import kr.mujuthaek.api.common.exception.CustomException;
import kr.mujuthaek.api.common.exception.ErrorCode;
import kr.mujuthaek.api.common.id.UuidV7;
import kr.mujuthaek.api.eligibility.dto.request.AdminCriteriaRequest;
import kr.mujuthaek.api.eligibility.dto.request.RegulatedAreaRequest;
import kr.mujuthaek.api.eligibility.dto.response.AdminCriteriaResponse;
import kr.mujuthaek.api.eligibility.dto.response.AdminCriteriaResponse.Change;
import kr.mujuthaek.api.eligibility.dto.response.AdminCriteriaResponse.Changes;
import kr.mujuthaek.api.eligibility.dto.response.AdminCriteriaResponse.Year;
import kr.mujuthaek.api.eligibility.dto.response.CriteriaUsageResponse;
import kr.mujuthaek.api.eligibility.dto.response.RegulatedAreaResponse;
import kr.mujuthaek.api.eligibility.repository.CriteriaAdminStore;
import kr.mujuthaek.api.eligibility.repository.CriteriaAdminStore.CriteriaSet;
import kr.mujuthaek.api.eligibility.repository.CriteriaAdminStore.RegulatedArea;
import kr.mujuthaek.api.notice.service.NoticeField;
import kr.mujuthaek.api.notice.service.NoticeForJudgment;
import kr.mujuthaek.api.notice.service.NoticeQueryService;
import kr.mujuthaek.api.notice.service.ProgramForJudgment;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

/**
 * 관리자 기준값 화면: 연도별 기준값 넣기·예약 적용·바꾼 기록, 규제지역 지정·해제. 판정은 {@link CriteriaService}가 같은 표를 읽어요(쓰기 시작하는 날이
 * 오면 그 해 값을 써요).
 *
 * <p>값의 모양만 검사해요. 금액이 고시와 맞는지는 넣는 사람이 근거(source)와 함께 확인해요.
 */
@Service
public class AdminCriteriaService {

  public static final Set<String> KINDS =
      Set.of("MEDIAN_INCOME", "URBAN_WORKER_INCOME", "RANK_CRITERIA");
  private static final ZoneId SEOUL = ZoneId.of("Asia/Seoul");
  private static final int HISTORY_LIMIT = 100;

  private final CriteriaAdminStore store;
  private final NoticeQueryService notices;
  private final JsonMapper json;
  private final Clock clock;

  public AdminCriteriaService(
      CriteriaAdminStore store, NoticeQueryService notices, JsonMapper json, Clock clock) {
    this.store = store;
    this.notices = notices;
    this.json = json;
    this.clock = clock;
  }

  /**
   * 「이 값을 쓰는 규칙 N개」: 열린 공고·창업지원 사업(notice의 판정용 조회)의 판정 틀에서 이 기준을 쓰는 것을 세요. 소득 기준은 조건의 standard, 순위
   * 요건은 신청 순위(rank)가 있는 대상군으로 봐요.
   */
  public CriteriaUsageResponse usage(String kind) {
    checkKind(kind);
    int housing =
        count(
            kind,
            notices.findOpenForJudgment(NoticeField.HOUSING).stream()
                .map(NoticeForJudgment::frame));
    int space =
        count(
            kind,
            notices.findOpenForJudgment(NoticeField.BUSINESS_SPACE).stream()
                .map(NoticeForJudgment::frame));
    int startup =
        count(kind, notices.findOpenProgramsForJudgment().stream().map(ProgramForJudgment::frame));
    return new CriteriaUsageResponse(kind, housing, space, startup, housing + space + startup);
  }

  static int count(String kind, Stream<JsonNode> frames) {
    return (int) frames.filter(f -> f != null && uses(kind, f)).count();
  }

  /** 판정 틀(아무 깊이)에서 이 기준을 쓰는지. */
  static boolean uses(String kind, JsonNode node) {
    if (node.isObject()) {
      if ("RANK_CRITERIA".equals(kind)) {
        if (node.path("rank").isIntegralNumber()) {
          return true;
        }
      } else {
        String standard = node.path("standard").asString("");
        if (kind.equals(standard)
            || ("URBAN_WORKER_INCOME".equals(kind)
                && "URBAN_WORKER_AVERAGE_INCOME".equals(standard))) {
          return true;
        }
      }
      for (var entry : node.properties()) {
        if (uses(kind, entry.getValue())) {
          return true;
        }
      }
      return false;
    }
    if (node.isArray()) {
      for (JsonNode item : node) {
        if (uses(kind, item)) {
          return true;
        }
      }
    }
    return false;
  }

  @Transactional(readOnly = true)
  public AdminCriteriaResponse criteria(String kind) {
    checkKind(kind);
    List<CriteriaSet> sets = store.sets(kind);
    LocalDate today = today();
    Integer inEffect =
        sets.stream()
            .filter(s -> !s.validFrom().isAfter(today))
            .map(CriteriaSet::year)
            .max(Integer::compare)
            .orElse(null);
    return new AdminCriteriaResponse(
        kind,
        sets.stream()
            .map(
                s ->
                    new Year(
                        s.year(),
                        s.validFrom(),
                        s.validFrom().isAfter(today)
                            ? "SCHEDULED"
                            : Integer.valueOf(s.year()).equals(inEffect) ? "IN_EFFECT" : "PAST",
                        json.readTree(s.data()),
                        s.source(),
                        s.updatedBy(),
                        s.updatedAt()))
            .toList());
  }

  /** 적용 시작일이 그 해 밖이면 「어느 해 값을 쓸지」가 어긋나요(2026-10-25 검토). */
  static void checkValidFrom(int year, LocalDate validFrom) {
    if (validFrom.getYear() != year) {
      throw new CustomException(ErrorCode.VALIDATION_FAILED, "적용 시작일은 " + year + "년 안이어야 해요");
    }
  }

  /** 한 해 값 넣기·바꾸기. 바꾸면 바꾸기 전 값을 기록에 남겨요. */
  @Transactional
  public AdminCriteriaResponse save(
      String kind, int year, AdminCriteriaRequest request, String admin) {
    checkKind(kind);
    if (year < 2000 || year > 2200) {
      throw new CustomException(ErrorCode.VALIDATION_FAILED, "year는 2000~2200 사이예요");
    }
    checkData(kind, request.data());
    LocalDate validFrom =
        request.validFrom() != null ? request.validFrom() : LocalDate.of(year, 1, 1);
    checkValidFrom(year, validFrom);
    store.save(
        kind,
        year,
        validFrom,
        json.writeValueAsString(request.data()),
        blankToNull(request.source()),
        admin);
    return criteria(kind);
  }

  @Transactional(readOnly = true)
  public Changes history(String kind) {
    checkKind(kind);
    return new Changes(
        kind,
        store.history(kind, HISTORY_LIMIT).stream()
            .map(
                h ->
                    new Change(
                        h.before().year(),
                        h.before().validFrom(),
                        json.readTree(h.before().data()),
                        h.before().source(),
                        h.replacedAt(),
                        h.replacedBy()))
            .toList());
  }

  @Transactional(readOnly = true)
  public List<RegulatedAreaResponse> regulatedAreas(boolean activeOnly) {
    LocalDate today = today();
    return store.regulatedAreas(activeOnly ? today : null).stream()
        .map(a -> view(a, today))
        .toList();
  }

  @Transactional
  public RegulatedAreaResponse addRegulatedArea(RegulatedAreaRequest request, String admin) {
    if (request.validUntil() != null && request.validUntil().isBefore(request.validFrom())) {
      throw new CustomException(ErrorCode.VALIDATION_FAILED, "해제일은 지정일보다 앞설 수 없어요");
    }
    UUID id = UuidV7.next();
    store.addRegulatedArea(
        new RegulatedArea(
            id,
            request.regionCode(),
            request.kind().name(),
            blankToNull(request.scopeNote()),
            request.validFrom(),
            request.validUntil(),
            blankToNull(request.source()),
            admin,
            null));
    return view(store.findRegulatedArea(id).orElseThrow(), today());
  }

  /** 해제. 해제일이 지정일보다 앞서면 거절해요. */
  @Transactional
  public RegulatedAreaResponse endRegulatedArea(UUID id, LocalDate until, String admin) {
    RegulatedArea area =
        store
            .findRegulatedArea(id)
            .orElseThrow(() -> new CustomException(ErrorCode.NOT_FOUND, "규제지역을 찾을 수 없어요"));
    LocalDate day = until != null ? until : today();
    if (store.endRegulatedArea(id, day, admin) == 0) {
      throw new CustomException(
          ErrorCode.VALIDATION_FAILED, "해제일은 지정일(" + area.validFrom() + ") 뒤여야 해요");
    }
    return view(store.findRegulatedArea(id).orElseThrow(), today());
  }

  static void checkData(String kind, JsonNode data) {
    if (data == null || !data.isObject()) {
      throw new CustomException(ErrorCode.VALIDATION_FAILED, "data는 JSON 객체여야 해요");
    }
    if ("RANK_CRITERIA".equals(kind)) {
      if (!data.path("ranks").isArray() && !data.path("byNoticeType").isObject()) {
        throw new CustomException(
            ErrorCode.VALIDATION_FAILED, "순위 요건은 ranks 목록이나 byNoticeType이 있어야 해요");
      }
      return;
    }
    JsonNode monthly = data.path("monthlyWon");
    if (!monthly.isObject() || monthly.isEmpty() || !monthly.has("1")) {
      throw new CustomException(
          ErrorCode.VALIDATION_FAILED, "소득 기준은 monthlyWon에 1인 가구부터 금액이 있어야 해요");
    }
    for (var entry : monthly.properties()) {
      if (!entry.getKey().matches("^[1-9][0-9]?$")) {
        throw new CustomException(
            ErrorCode.VALIDATION_FAILED, "monthlyWon의 키는 가구원 수(1, 2, …)예요: " + entry.getKey());
      }
      if (!entry.getValue().isIntegralNumber() || entry.getValue().asLong() <= 0) {
        throw new CustomException(
            ErrorCode.VALIDATION_FAILED, "monthlyWon의 금액은 0보다 큰 원 단위 정수예요: " + entry.getKey());
      }
    }
  }

  private static void checkKind(String kind) {
    if (!KINDS.contains(kind)) {
      throw new CustomException(
          ErrorCode.VALIDATION_FAILED,
          "kind는 MEDIAN_INCOME·URBAN_WORKER_INCOME·RANK_CRITERIA 중 하나예요");
    }
  }

  private static RegulatedAreaResponse view(RegulatedArea a, LocalDate today) {
    boolean active =
        !a.validFrom().isAfter(today)
            && (a.validUntil() == null || !a.validUntil().isBefore(today));
    return new RegulatedAreaResponse(
        a.id(),
        a.regionCode(),
        a.kind(),
        a.scopeNote(),
        a.validFrom(),
        a.validUntil(),
        active,
        a.source(),
        a.updatedBy(),
        a.updatedAt());
  }

  private LocalDate today() {
    return LocalDate.now(clock.withZone(SEOUL));
  }

  private static String blankToNull(String value) {
    return value == null || value.isBlank() ? null : value.trim();
  }
}
