package kr.mujuthaek.api.eligibility.service;

import java.time.LocalDate;
import java.util.Comparator;
import java.util.List;
import java.util.Objects;
import kr.mujuthaek.api.common.dto.response.CursorPageResponse;
import kr.mujuthaek.api.common.pagination.CursorKey;
import kr.mujuthaek.api.common.pagination.CursorQuery;
import kr.mujuthaek.api.eligibility.dto.request.NoticeSearchRequest;
import kr.mujuthaek.api.eligibility.dto.response.NoticeEvaluationResponse;
import kr.mujuthaek.api.eligibility.dto.response.NoticeSearchResponse;
import kr.mujuthaek.api.eligibility.rule.Applicant;
import kr.mujuthaek.api.eligibility.rule.Overall;
import kr.mujuthaek.api.eligibility.rule.PrepareCost;
import kr.mujuthaek.api.notice.service.NoticeQueryService;
import org.springframework.stereotype.Service;

/**
 * 맞춤 목록: 필터로 접수예정·접수중 공고를 먼저 줄이고, 공고마다 판정·준비할 돈을 계산해 정렬해요.
 *
 * <p>판정은 계산값이라 DB에서 정렬할 수 없어요. 그래서 후보를 최대 {@link #MAX_CANDIDATES}개까지만 보고, 목록 안 위치를 커서로 써요. 판정 입력은
 * 저장하지 않아요. eligibility → notice 호출이라 이 모듈에 둬요 (notice는 eligibility를 부를 수 없어요).
 */
@Service
public class NoticeSearchService {

  static final int MAX_CANDIDATES = 300;

  private final NoticeQueryService notices;
  private final NoticeEvaluationService evaluations;
  private final JudgingFrames frames;

  public NoticeSearchService(
      NoticeQueryService notices, NoticeEvaluationService evaluations, JudgingFrames frames) {
    this.notices = notices;
    this.evaluations = evaluations;
    this.frames = frames;
  }

  public NoticeSearchResponse search(NoticeSearchRequest request) {
    var f = request.filtersOrEmpty();
    String sort = request.sortOrDefault();
    CursorQuery page = CursorQuery.of(request.cursor(), request.size(), sort);
    Applicant applicant =
        request.applicant() == null ? Applicant.empty() : request.applicant().toApplicant();
    List<NoticeSearchResponse.Item> judged = judgeAll(f, applicant);
    var counts =
        new NoticeSearchResponse.Counts(
            count(judged, Overall.ELIGIBLE),
            count(judged, Overall.NEEDS_INPUT),
            count(judged, Overall.INELIGIBLE));
    boolean includeIneligible = Boolean.TRUE.equals(request.includeIneligible());
    List<NoticeSearchResponse.Item> shown =
        judged.stream()
            .filter(i -> includeIneligible || i.overall() != Overall.INELIGIBLE)
            .sorted(order(sort))
            .toList();
    int from = page.after() == null ? 0 : page.after().position() + 1;
    List<Integer> positions =
        java.util.stream.IntStream.range(Math.min(from, shown.size()), shown.size())
            .limit(page.fetchSize())
            .boxed()
            .toList();
    var pageOf =
        CursorPageResponse.from(
            positions, page.size(), shown::get, i -> CursorKey.of(sort, i, shown.get(i).id()));
    return new NoticeSearchResponse(counts, pageOf.items(), pageOf.nextCursor(), pageOf.hasNext());
  }

  /** 필터에 맞는 후보(최대 {@link #MAX_CANDIDATES}개, 마감 임박순)를 모두 판정해요. 지원 불가도 들어 있어요. 맞춤 목록과 홈 요약이 같이 써요. */
  public List<NoticeSearchResponse.Item> judgeAll(
      NoticeSearchRequest.Filters f, Applicant applicant) {
    List<NoticeQueryService.Candidate> candidates =
        notices.searchCandidates(
            f.field(),
            f.regionCodes(),
            f.tenure(),
            f.noticeTypes(),
            f.providers(),
            f.statuses(),
            f.keyword(),
            MAX_CANDIDATES);
    // 판정 틀은 한 번에 읽고(기억해 둔 건 다시 안 읽어요), 기준 소득·대출 상품도 요청마다 한 번만 읽어요
    var sources = frames.frames(candidates.stream().map(NoticeQueryService.Candidate::id).toList());
    var evaluate = evaluations.evaluator(applicant);
    return candidates.stream()
        .filter(c -> sources.containsKey(c.id())) // 그 사이 숨겨진 공고는 빼요
        .map(c -> item(c, evaluate.apply(sources.get(c.id()))))
        .toList();
  }

  private static NoticeSearchResponse.Item item(
      NoticeQueryService.Candidate c, NoticeEvaluationResponse e) {
    Long prepare =
        e.unitTypes().stream()
            .map(u -> u.prepareCost().prepareWon())
            .filter(Objects::nonNull)
            .min(Long::compare)
            .orElse(null);
    String note =
        prepare != null
            ? null
            : e.unitTypes().stream()
                .map(NoticeEvaluationResponse.UnitType::prepareCost)
                .map(PrepareCost.Result::note)
                .filter(Objects::nonNull)
                .findFirst()
                .orElse("PRICE_NOT_ANNOUNCED");
    return new NoticeSearchResponse.Item(
        c.id(),
        c.title(),
        c.provider(),
        c.noticeType(),
        c.regionCode(),
        c.regionName(),
        c.status(),
        c.applyStart(),
        c.applyEnd(),
        c.dday(),
        c.postedOn(),
        e.overall(),
        prepare,
        note,
        c.areaScore(),
        null,
        c.tags(),
        c.lat(),
        c.lng(),
        c.siteCount());
  }

  /**
   * RECOMMENDED: 지원 가능 → 확인 필요 → 지원 불가, 같으면 마감 임박, 그다음 생활권 총점 높은 순. PREPARE_COST: 준비할 돈 적은 순 (모르면
   * 뒤). AREA_SCORE: 생활권 총점 높은 순 (없으면 뒤). 관심 지역 순서는 관심 지역을 서버에 저장하게 되면 붙여요.
   */
  static Comparator<NoticeSearchResponse.Item> order(String sort) {
    Comparator<NoticeSearchResponse.Item> deadline =
        Comparator.comparing(
            NoticeSearchResponse.Item::applyEnd,
            Comparator.nullsLast(Comparator.<LocalDate>naturalOrder()));
    Comparator<NoticeSearchResponse.Item> areaScore =
        Comparator.comparing(
            NoticeSearchResponse.Item::areaScore,
            Comparator.nullsLast(Comparator.<Integer>reverseOrder()));
    Comparator<NoticeSearchResponse.Item> byId =
        Comparator.comparing(NoticeSearchResponse.Item::id);
    return switch (sort) {
      case "DEADLINE" -> deadline.thenComparing(byId);
      case "PREPARE_COST" ->
          Comparator.comparing(
                  NoticeSearchResponse.Item::prepareCostWon,
                  Comparator.nullsLast(Comparator.<Long>naturalOrder()))
              .thenComparing(deadline)
              .thenComparing(byId);
      case "AREA_SCORE" -> areaScore.thenComparing(byId);
      default ->
          Comparator.comparing((NoticeSearchResponse.Item i) -> i.overall().ordinal())
              .thenComparing(deadline)
              .thenComparing(areaScore)
              .thenComparing(byId);
    };
  }

  private static int count(List<NoticeSearchResponse.Item> items, Overall overall) {
    return (int) items.stream().filter(i -> i.overall() == overall).count();
  }
}
