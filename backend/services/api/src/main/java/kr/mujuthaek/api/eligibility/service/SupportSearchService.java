package kr.mujuthaek.api.eligibility.service;

import java.time.Clock;
import java.time.LocalDate;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.regex.Pattern;
import java.util.stream.IntStream;
import kr.mujuthaek.api.common.dto.response.CursorPageResponse;
import kr.mujuthaek.api.common.exception.CustomException;
import kr.mujuthaek.api.common.exception.ErrorCode;
import kr.mujuthaek.api.common.pagination.CursorKey;
import kr.mujuthaek.api.common.pagination.CursorQuery;
import kr.mujuthaek.api.common.text.Keywords;
import kr.mujuthaek.api.eligibility.dto.request.JudgmentApplicantRequest;
import kr.mujuthaek.api.eligibility.dto.request.SupportSearchRequest;
import kr.mujuthaek.api.eligibility.dto.response.SupportEvaluationResponse;
import kr.mujuthaek.api.eligibility.dto.response.SupportSearchResponse;
import kr.mujuthaek.api.eligibility.model.MatchResult;
import kr.mujuthaek.api.eligibility.rule.Eligibility;
import kr.mujuthaek.api.notice.service.NoticeQueryService;
import org.springframework.stereotype.Service;

/**
 * 사업 지원(창업지원 사업) 맞춤 목록·판정. 열린 창업지원 사업(K-Startup·기업마당)을 창업지원 판정 틀로 판정해요. 사업 상세 API가 없어서 상세는 판정 응답과
 * 원문으로 보여줘요. 지역 거르기·출처·같은 사업 하나만 남기기는 사업공간({@link SpaceSearchService})과 같아요.
 *
 * <p>API 설계는 혜택 API(/benefits/search, fields=STARTUP)였지만, 창업지원은 혜택 표가 아니라 판정
 * 틀(notice.policy_judgments)로만 들어와서 사업공간과 같은 모양으로 따로 열어요. 판정 입력은 저장하지 않아요.
 */
@Service
public class SupportSearchService {

  static final String FUND = "FUND";
  private static final List<String> SUB_FIELDS = List.of(FUND, "LOAN", "TAX");
  private static final Pattern LOAN = Pattern.compile("융자|대출|보증|정책\\s*자금");
  private static final Pattern TAX = Pattern.compile("세액|세금|감면|면세|비과세");

  private final MatchQueryService matches;
  private final NoticeQueryService notices;
  private final Clock clock;

  SupportSearchService(MatchQueryService matches, NoticeQueryService notices, Clock clock) {
    this.matches = matches;
    this.notices = notices;
    this.clock = clock;
  }

  public SupportSearchResponse search(SupportSearchRequest request) {
    var f = request.filtersOrEmpty();
    String sort = request.sortOrDefault();
    CursorQuery page = CursorQuery.of(request.cursor(), request.size(), sort);
    LocalDate today = LocalDate.now(clock);
    List<MatchResult.Item> matched =
        matches.judgeStartupSupportAll(request.applicant()).stream()
            .filter(m -> SpaceSearchService.inRegions(m.regionCodes(), f.regionCodes()))
            .toList();
    Map<UUID, NoticeQueryService.PolicyInfo> infos =
        notices.policyInfos(matched.stream().map(MatchResult.Item::noticeId).toList());
    Keywords keywords = Keywords.of(f.keyword());
    List<SupportSearchResponse.Item> inRegion =
        withoutDuplicates(
                matched.stream().map(m -> item(m, infos.get(m.noticeId()), today)).toList())
            .stream()
            .filter(i -> keywords.matches(i.title(), i.organization()))
            .toList();
    Map<String, Integer> subFieldCounts = new LinkedHashMap<>();
    SUB_FIELDS.forEach(t -> subFieldCounts.put(t, 0));
    inRegion.forEach(i -> subFieldCounts.merge(i.subField(), 1, Integer::sum));
    List<SupportSearchResponse.Item> judged =
        inRegion.stream()
            .filter(
                i ->
                    f.subFields() == null
                        || f.subFields().isEmpty()
                        || f.subFields().contains(i.subField()))
            .toList();
    var counts =
        new SupportSearchResponse.Counts(
            count(judged, Eligibility.ELIGIBLE),
            count(judged, Eligibility.NEEDS_INPUT),
            count(judged, Eligibility.INELIGIBLE));
    boolean includeIneligible = Boolean.TRUE.equals(request.includeIneligible());
    List<SupportSearchResponse.Item> shown =
        judged.stream()
            .filter(i -> includeIneligible || i.overall() != Eligibility.INELIGIBLE)
            .sorted(order(sort))
            .toList();
    int from = page.after() == null ? 0 : page.after().position() + 1;
    List<Integer> positions =
        IntStream.range(Math.min(from, shown.size()), shown.size())
            .limit(page.fetchSize())
            .boxed()
            .toList();
    var pageOf =
        CursorPageResponse.from(
            positions, page.size(), shown::get, i -> CursorKey.of(sort, i, shown.get(i).id()));
    return new SupportSearchResponse(
        counts, subFieldCounts, pageOf.items(), pageOf.nextCursor(), pageOf.hasNext());
  }

  /** 열린 창업지원 사업 하나의 판정. 열린 사업이 아니면 404 NOTICE_NOT_FOUND. */
  public SupportEvaluationResponse evaluate(UUID id, JudgmentApplicantRequest applicant) {
    var j =
        matches
            .judgeStartupSupport(id, applicant)
            .orElseThrow(() -> new CustomException(ErrorCode.NOTICE_NOT_FOUND));
    var n = j.notice();
    LocalDate today = LocalDate.now(clock);
    NoticeQueryService.PolicyInfo info = notices.policyInfos(List.of(id)).get(id);
    return new SupportEvaluationResponse(
        id,
        SpaceSearchService.source(n.detailUrl()),
        subField(info == null ? null : info.supportArea(), n.title()),
        n.title(),
        n.detailUrl(),
        n.applyStart(),
        n.applyEnd(),
        SpaceSearchService.dday(n.applyEnd(), today),
        SpaceSearchService.status(n.applyStart(), n.applyEnd(), today),
        n.regionCodes(),
        info,
        j.judgment());
  }

  /**
   * 지원 종류: 출처의 지원 분야(예: 융자 · 사업화)가 있으면 그걸로, 없으면 이름으로 정해요. 융자·대출·보증·정책자금이면 정책자금, 세액·감면이면 세금 감면, 나머지는
   * 지원금.
   */
  static String subField(String supportArea, String title) {
    String name = (supportArea == null ? "" : supportArea + " ") + (title == null ? "" : title);
    if (TAX.matcher(name).find()) {
      return "TAX";
    }
    return LOAN.matcher(name).find() ? "LOAN" : FUND;
  }

  private static SupportSearchResponse.Item item(
      MatchResult.Item m, NoticeQueryService.PolicyInfo info, LocalDate today) {
    return new SupportSearchResponse.Item(
        m.noticeId(),
        SpaceSearchService.source(m.detailUrl()),
        subField(info == null ? null : info.supportArea(), m.title()),
        info == null ? null : info.supportArea(),
        info == null ? null : info.organization(),
        info == null ? null : info.amountText(),
        m.title(),
        m.regionCodes(),
        SpaceSearchService.status(m.applyStart(), m.applyEnd(), today),
        m.applyStart(),
        m.applyEnd(),
        SpaceSearchService.dday(m.applyEnd(), today),
        m.status(),
        m.reason(),
        m.groups(),
        m.missingInputs(),
        m.detailUrl(),
        info == null ? null : info.applyNote());
  }

  /**
   * 같은 사업이 K-Startup·기업마당에 같이 올라오면 하나만, K-Startup을 남겨요 (같은지는 {@link
   * SpaceSearchService#sameProgram}).
   */
  static List<SupportSearchResponse.Item> withoutDuplicates(
      List<SupportSearchResponse.Item> items) {
    return SpaceSearchService.withoutDuplicates(
        items,
        SupportSearchResponse.Item::title,
        SupportSearchResponse.Item::applyEnd,
        SupportSearchService::preference);
  }

  private static int preference(SupportSearchResponse.Item i) {
    if ("KSTARTUP".equals(i.source())) {
      return 0;
    }
    return "BIZINFO".equals(i.source()) ? 1 : 2;
  }

  /** RECOMMENDED: 지원 가능 → 확인 필요 → 지원 불가, 같으면 마감 임박(마감 없음은 뒤). DEADLINE: 마감 임박. */
  static Comparator<SupportSearchResponse.Item> order(String sort) {
    Comparator<SupportSearchResponse.Item> deadline =
        Comparator.comparing(
            SupportSearchResponse.Item::applyEnd,
            Comparator.nullsLast(Comparator.<LocalDate>naturalOrder()));
    Comparator<SupportSearchResponse.Item> byId =
        Comparator.comparing(SupportSearchResponse.Item::id);
    if ("DEADLINE".equals(sort)) {
      return deadline.thenComparing(byId);
    }
    return Comparator.comparing((SupportSearchResponse.Item i) -> i.overall().ordinal())
        .thenComparing(deadline)
        .thenComparing(byId);
  }

  private static int count(List<SupportSearchResponse.Item> items, Eligibility overall) {
    return (int) items.stream().filter(i -> i.overall() == overall).count();
  }
}
