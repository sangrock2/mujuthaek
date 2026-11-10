package kr.mujuthaek.api.eligibility.service;

import java.time.Clock;
import java.time.LocalDate;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.function.Function;
import java.util.stream.Collectors;
import java.util.stream.IntStream;
import kr.mujuthaek.api.common.dto.response.CursorPageResponse;
import kr.mujuthaek.api.common.exception.CustomException;
import kr.mujuthaek.api.common.exception.ErrorCode;
import kr.mujuthaek.api.common.pagination.CursorKey;
import kr.mujuthaek.api.common.pagination.CursorQuery;
import kr.mujuthaek.api.common.region.CityDistricts;
import kr.mujuthaek.api.common.text.Keywords;
import kr.mujuthaek.api.eligibility.dto.request.JudgmentApplicantRequest;
import kr.mujuthaek.api.eligibility.dto.request.SpaceSearchRequest;
import kr.mujuthaek.api.eligibility.dto.response.SpaceEvaluationResponse;
import kr.mujuthaek.api.eligibility.dto.response.SpaceSearchResponse;
import kr.mujuthaek.api.eligibility.model.MatchResult;
import kr.mujuthaek.api.eligibility.rule.Eligibility;
import kr.mujuthaek.api.notice.service.NoticeQueryService;
import org.springframework.stereotype.Service;

/**
 * 사업공간 맞춤 목록·판정. 열린 사업공간 공고와 사업공간 모집 정책(K-Startup·기업마당 입주기업 모집)을 사업공간 판정 틀로 판정하고, 공고면 목록 정보(기관·종류·
 * 지역 이름·세권 태그)를 붙여요.
 *
 * <p>판정은 계산값이라 DB에서 정렬할 수 없어요. 열린 사업공간 전부를 판정하고 목록 안 위치를 커서로 써요. 판정 입력은 저장하지 않아요.
 */
@Service
public class SpaceSearchService {

  static final String STARTUP_SPACE = "STARTUP_SPACE";
  private static final List<String> SPACE_TYPES =
      List.of(STARTUP_SPACE, "SHOP_RENTAL", "MEETING_ROOM");
  private static final int MAX_NOTICES = 300;

  private final MatchQueryService matches;
  private final NoticeQueryService notices;
  private final Clock clock;

  SpaceSearchService(MatchQueryService matches, NoticeQueryService notices, Clock clock) {
    this.matches = matches;
    this.notices = notices;
    this.clock = clock;
  }

  public SpaceSearchResponse search(SpaceSearchRequest request) {
    var f = request.filtersOrEmpty();
    String sort = request.sortOrDefault();
    CursorQuery page = CursorQuery.of(request.cursor(), request.size(), sort);
    LocalDate today = LocalDate.now(clock);
    Map<UUID, NoticeQueryService.Candidate> info =
        notices
            .searchCandidates("BUSINESS_SPACE", null, null, null, null, null, null, MAX_NOTICES)
            .stream()
            .collect(Collectors.toMap(NoticeQueryService.Candidate::id, Function.identity()));
    List<MatchResult.Item> matched =
        matches.judgeBusinessSpaceAll(request.applicant()).stream()
            .filter(m -> inRegions(m.regionCodes(), f.regionCodes()))
            .toList();
    Map<UUID, NoticeQueryService.PolicyInfo> infos =
        notices.policyInfos(
            matched.stream()
                .filter(MatchResult.Item::policy)
                .map(MatchResult.Item::noticeId)
                .toList());
    Keywords keywords = Keywords.of(f.keyword());
    List<SpaceSearchResponse.Item> inRegion =
        withoutDuplicates(
                matched.stream()
                    .map(m -> item(m, info.get(m.noticeId()), infos.get(m.noticeId()), today))
                    .toList())
            .stream()
            .filter(i -> keywords.matches(i.title(), i.organization()))
            .toList();
    Map<String, Integer> typeCounts = new LinkedHashMap<>();
    SPACE_TYPES.forEach(t -> typeCounts.put(t, 0));
    inRegion.forEach(i -> typeCounts.merge(i.spaceType(), 1, Integer::sum));
    List<SpaceSearchResponse.Item> judged =
        inRegion.stream()
            .filter(
                i ->
                    f.spaceTypes() == null
                        || f.spaceTypes().isEmpty()
                        || f.spaceTypes().contains(i.spaceType()))
            .toList();
    var counts =
        new SpaceSearchResponse.Counts(
            count(judged, Eligibility.ELIGIBLE),
            count(judged, Eligibility.NEEDS_INPUT),
            count(judged, Eligibility.INELIGIBLE));
    boolean includeIneligible = Boolean.TRUE.equals(request.includeIneligible());
    List<SpaceSearchResponse.Item> shown =
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
    return new SpaceSearchResponse(
        counts, typeCounts, pageOf.items(), pageOf.nextCursor(), pageOf.hasNext());
  }

  /** 열린 사업공간 하나의 판정. 열린 사업공간이 아니면 404 NOTICE_NOT_FOUND. */
  public SpaceEvaluationResponse evaluate(UUID id, JudgmentApplicantRequest applicant) {
    var j =
        matches
            .judgeBusinessSpace(id, applicant)
            .orElseThrow(() -> new CustomException(ErrorCode.NOTICE_NOT_FOUND));
    var n = j.notice();
    LocalDate today = LocalDate.now(clock);
    return new SpaceEvaluationResponse(
        id,
        n.policy(),
        n.policy() ? source(n.detailUrl()) : null,
        n.title(),
        n.detailUrl(),
        n.applyStart(),
        n.applyEnd(),
        dday(n.applyEnd(), today),
        status(n.applyStart(), n.applyEnd(), today),
        n.regionCodes(),
        n.policy() ? notices.policyInfos(List.of(id)).get(id) : null,
        j.judgment());
  }

  /** 모집 정책의 출처: 원문 주소의 기관 사이트로 정해요 (판정 틀에는 출처 칸이 없어요). */
  static String source(String detailUrl) {
    if (detailUrl == null) {
      return null;
    }
    if (detailUrl.contains("k-startup.go.kr")) {
      return "KSTARTUP";
    }
    return detailUrl.contains("bizinfo.go.kr") ? "BIZINFO" : null;
  }

  /**
   * 같은 모집이 여러 출처(K-Startup·기업마당)에 올라오면 하나만 남겨요({@link #sameProgram}). 공고 → K-Startup(원문 본문까지 읽음) →
   * 기업마당 → 출처 모름 순으로 남기고, 처음 순서는 그대로예요.
   */
  static List<SpaceSearchResponse.Item> withoutDuplicates(List<SpaceSearchResponse.Item> items) {
    return withoutDuplicates(
        items,
        SpaceSearchResponse.Item::title,
        SpaceSearchResponse.Item::applyEnd,
        SpaceSearchService::preference);
  }

  /** 같은 모집끼리 preference가 작은 것 하나만 남겨요. 처음 순서는 그대로예요 (사업공간·사업 지원 같이 써요). */
  static <T> List<T> withoutDuplicates(
      List<T> items,
      java.util.function.Function<T, String> title,
      java.util.function.Function<T, LocalDate> applyEnd,
      java.util.function.ToIntFunction<T> preference) {
    List<T> kept = new java.util.ArrayList<>();
    for (T item : items) {
      int same = -1;
      for (int k = 0; k < kept.size() && same < 0; k++) {
        T other = kept.get(k);
        if (sameProgram(
            title.apply(item), applyEnd.apply(item), title.apply(other), applyEnd.apply(other))) {
          same = k;
        }
      }
      if (same < 0) {
        kept.add(item);
      } else if (preference.applyAsInt(item) < preference.applyAsInt(kept.get(same))) {
        kept.set(same, item);
      }
    }
    return items.stream().filter(kept::contains).toList();
  }

  /** 핵심 이름이 이보다 짧으면 포함 관계로 같다고 보지 않아요 (「창업 지원」처럼 흔한 이름끼리 묶이지 않게). */
  private static final int MIN_CONTAINED = 10;

  /**
   * 같은 모집인지: 핵심 이름이 같으면(마감일을 하나라도 모르면 그대로) 같고, 아니면 마감일이 같으면서(둘 다 상시면 같음) 한쪽이 다른 쪽을 품으면 같아요. 핵심 이름은
   * 대괄호·괄호 안 말(지역 머리말 [충북] · 마감 표시 (~11.3))과 「공고」를 빼고 글자·숫자만 남긴 것이에요. 예: 「&lt;2026년 시제품 고도화 바우처 지원
   * 프로그램&gt; 참여 기업 모집 (~11.3.14시)」 · 「[충북] 청주시 2026년 시제품 고도화 바우처 지원 프로그램 참여 기업 모집 공고」
   */
  static boolean sameProgram(String a, LocalDate endA, String b, LocalDate endB) {
    String ka = titleKey(a);
    String kb = titleKey(b);
    if (ka.isEmpty() || kb.isEmpty()) {
      return false;
    }
    if (ka.equals(kb)) {
      return endA == null || endB == null || endA.equals(endB);
    }
    if (!java.util.Objects.equals(endA, endB)) {
      return false;
    }
    String shorter = ka.length() <= kb.length() ? ka : kb;
    String longer = shorter == ka ? kb : ka;
    return shorter.length() >= MIN_CONTAINED && longer.contains(shorter);
  }

  static String titleKey(String title) {
    if (title == null) {
      return "";
    }
    return title
        .replaceAll("\\[[^\\]]*\\]|\\([^)]*\\)", "")
        .replace("공고", "")
        .replaceAll("[^\\p{IsHangul}\\p{Alnum}]", "")
        .toLowerCase();
  }

  private static int preference(SpaceSearchResponse.Item i) {
    if (!i.policy()) {
      return 0;
    }
    if ("KSTARTUP".equals(i.source())) {
      return 1;
    }
    return "BIZINFO".equals(i.source()) ? 2 : 3;
  }

  private static SpaceSearchResponse.Item item(
      MatchResult.Item m,
      NoticeQueryService.Candidate c,
      NoticeQueryService.PolicyInfo policyInfo,
      LocalDate today) {
    return new SpaceSearchResponse.Item(
        m.noticeId(),
        m.policy(),
        m.policy() ? source(m.detailUrl()) : null,
        c != null && c.noticeType() != null ? c.noticeType() : STARTUP_SPACE,
        m.title(),
        c == null ? null : c.provider(),
        policyInfo == null ? null : policyInfo.organization(),
        c == null ? null : c.regionName(),
        m.regionCodes(),
        c != null ? c.status() : status(m.applyStart(), m.applyEnd(), today),
        m.applyStart(),
        m.applyEnd(),
        dday(m.applyEnd(), today),
        m.status(),
        m.reason(),
        m.groups(),
        m.missingInputs(),
        m.detailUrl(),
        c == null ? List.of() : c.tags(),
        policyInfo == null ? null : policyInfo.applyNote());
  }

  /**
   * 마감까지 남은 날 (마감일 당일 0). 마감일이 없거나 지났으면 null. 공고 목록의 dday와 같은 규칙이에요 (notice 모듈 안 타입이라 여기서 같게 셈해요).
   */
  static Integer dday(LocalDate applyEnd, LocalDate today) {
    if (applyEnd == null || today.isAfter(applyEnd)) {
      return null;
    }
    return (int) java.time.temporal.ChronoUnit.DAYS.between(today, applyEnd);
  }

  /** 모집 정책은 접수 상태가 저장돼 있지 않아서 기간으로 정해요 (열린 것만 와요). */
  static String status(LocalDate applyStart, LocalDate applyEnd, LocalDate today) {
    if (applyEnd == null) {
      return "ALWAYS";
    }
    return applyStart != null && today.isBefore(applyStart) ? "UPCOMING" : "APPLYING";
  }

  /**
   * 고른 지역(시도 2자리·시군구 5자리)에 공간 지역(법정동코드 10자리)이 걸리는지. 고른 지역이 없거나, 전국 공간(빈 목록)이나 지역을 모르는 공간(null)은 늘
   * 걸려요. 공간 지역이 시도 전체(시군구 자리 000)면 그 시도의 시군구를 골라도 걸려요.
   */
  static boolean inRegions(List<String> spaceCodes, List<String> chosen) {
    if (chosen == null || chosen.isEmpty() || spaceCodes == null || spaceCodes.isEmpty()) {
      return true;
    }
    for (String code : spaceCodes) {
      if (code == null || code.length() < 5) {
        continue;
      }
      boolean wholeSido = code.startsWith("000", 2);
      for (String c : chosen) {
        // 일반구가 있는 시(CityDistricts): 시를 고르면 그 구의 공간도, 구를 고르면 시 전체 공간도 걸려요(재검토: 수원시를 고르면 구 공간이 빠졌음)
        if (code.startsWith(c)
            || (wholeSido && c.startsWith(code.substring(0, 2)))
            || CityDistricts.inCity(c, code)
            || (CityDistricts.isCity(code) && CityDistricts.inCity(code, c))) {
          return true;
        }
      }
    }
    return false;
  }

  /** RECOMMENDED: 지원 가능 → 확인 필요 → 지원 불가, 같으면 마감 임박(마감 없음은 뒤). DEADLINE: 마감 임박. */
  static Comparator<SpaceSearchResponse.Item> order(String sort) {
    Comparator<SpaceSearchResponse.Item> deadline =
        Comparator.comparing(
            SpaceSearchResponse.Item::applyEnd,
            Comparator.nullsLast(Comparator.<LocalDate>naturalOrder()));
    Comparator<SpaceSearchResponse.Item> byId = Comparator.comparing(SpaceSearchResponse.Item::id);
    if ("DEADLINE".equals(sort)) {
      return deadline.thenComparing(byId);
    }
    return Comparator.comparing((SpaceSearchResponse.Item i) -> i.overall().ordinal())
        .thenComparing(deadline)
        .thenComparing(byId);
  }

  private static int count(List<SpaceSearchResponse.Item> items, Eligibility overall) {
    return (int) items.stream().filter(i -> i.overall() == overall).count();
  }
}
