package kr.mujuthaek.api.eligibility.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.assertj.core.api.Assertions.entry;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import kr.mujuthaek.api.common.exception.CustomException;
import kr.mujuthaek.api.common.exception.ErrorCode;
import kr.mujuthaek.api.eligibility.dto.request.SpaceSearchRequest;
import kr.mujuthaek.api.eligibility.dto.response.SpaceEvaluationResponse;
import kr.mujuthaek.api.eligibility.dto.response.SpaceSearchResponse;
import kr.mujuthaek.api.eligibility.model.JudgmentResult;
import kr.mujuthaek.api.eligibility.model.MatchResult;
import kr.mujuthaek.api.eligibility.model.NoticeCandidate;
import kr.mujuthaek.api.eligibility.rule.Eligibility;
import kr.mujuthaek.api.notice.service.NoticeQueryService;
import org.junit.jupiter.api.Test;

/**
 * 사업공간 맞춤 목록·상세. 지역 거르기·모집 정책 접수 상태·정렬, 목록(거르기·개수·같은 모집 하나만·페이지)과 상세 응답을 봐요. 판정과 공고 정보는 가짜로 넣어요. 판정
 * 자체는 {@link MatchQueryServiceTest}에서 봐요.
 */
class SpaceSearchServiceTest {

  private static final UUID SHOP = UUID.fromString("00000000-0000-0000-0000-000000000021");
  private static final UUID KSTARTUP = UUID.fromString("00000000-0000-0000-0000-000000000022");
  private static final UUID BIZINFO = UUID.fromString("00000000-0000-0000-0000-000000000023");
  private static final UUID MAPO = UUID.fromString("00000000-0000-0000-0000-000000000024");
  private static final UUID BUSAN = UUID.fromString("00000000-0000-0000-0000-000000000025");
  private static final NoticeQueryService.PolicyInfo GTEC =
      new NoticeQueryService.PolicyInfo(
          "사업공간", null, "경기과학기술대학교 창업보육센터", null, null, null, null, null, "입주 심사 후 개별 안내");

  private final MatchQueryService matches = mock(MatchQueryService.class);
  private final NoticeQueryService notices = mock(NoticeQueryService.class);
  // 오늘은 2026-10-30 (한국 시간)
  private final SpaceSearchService spaces =
      new SpaceSearchService(
          matches,
          notices,
          Clock.fixed(Instant.parse("2026-10-30T01:00:00Z"), ZoneId.of("Asia/Seoul")));

  @Test
  void regionsMatchBySidoOrSigungu() {
    // 고른 지역이 없거나 전국(빈 목록)·지역 모름(null) 공간은 늘 걸려요
    assertThat(SpaceSearchService.inRegions(List.of("1120011500"), null)).isTrue();
    assertThat(SpaceSearchService.inRegions(List.of(), List.of("11200"))).isTrue();
    assertThat(SpaceSearchService.inRegions(null, List.of("11200"))).isTrue();
    // 시군구 5자리·시도 2자리로 골라요
    assertThat(SpaceSearchService.inRegions(List.of("1120011500"), List.of("11200"))).isTrue();
    assertThat(SpaceSearchService.inRegions(List.of("1120011500"), List.of("11"))).isTrue();
    assertThat(SpaceSearchService.inRegions(List.of("1120011500"), List.of("11440"))).isFalse();
    // 공간이 시도 전체면 그 시도의 시군구를 골라도 걸려요
    assertThat(SpaceSearchService.inRegions(List.of("1100000000"), List.of("11440"))).isTrue();
    assertThat(SpaceSearchService.inRegions(List.of("1100000000"), List.of("26110"))).isFalse();
    // 2026-11-10 재검토: 일반구가 있는 시를 고르면 그 구 공간도, 구를 고르면 시 전체 공간도 걸려요(수원시를 고르면 구 공간이 빠졌음)
    assertThat(SpaceSearchService.inRegions(List.of("4111112300"), List.of("41110"))).isTrue();
    assertThat(SpaceSearchService.inRegions(List.of("4111000000"), List.of("41111"))).isTrue();
    assertThat(SpaceSearchService.inRegions(List.of("4374510100"), List.of("43740"))).isFalse();
    assertThat(SpaceSearchService.inRegions(List.of("4374000000"), List.of("43745"))).isFalse();
  }

  @Test
  void policyStatusComesFromItsPeriod() {
    LocalDate today = LocalDate.parse("2026-10-26");
    assertThat(SpaceSearchService.status(null, null, today)).isEqualTo("ALWAYS");
    assertThat(
            SpaceSearchService.status(
                LocalDate.parse("2026-11-01"), LocalDate.parse("2026-11-10"), today))
        .isEqualTo("UPCOMING");
    assertThat(
            SpaceSearchService.status(
                LocalDate.parse("2026-10-20"), LocalDate.parse("2026-11-10"), today))
        .isEqualTo("APPLYING");
  }

  @Test
  void recommendedPutsEligibleFirstThenDeadline() {
    var late = item("00000000-0000-0000-0000-000000000001", Eligibility.ELIGIBLE, "2026-11-30");
    var soon = item("00000000-0000-0000-0000-000000000002", Eligibility.NEEDS_INPUT, "2026-10-30");
    var always = item("00000000-0000-0000-0000-000000000003", Eligibility.NEEDS_INPUT, null);
    var no = item("00000000-0000-0000-0000-000000000004", Eligibility.INELIGIBLE, "2026-10-27");
    List<SpaceSearchResponse.Item> items = List.of(no, always, soon, late);

    assertThat(items.stream().sorted(SpaceSearchService.order("RECOMMENDED")).toList())
        .containsExactly(late, soon, always, no);
    assertThat(items.stream().sorted(SpaceSearchService.order("DEADLINE")).toList())
        .containsExactly(no, soon, late, always);
  }

  @Test
  void sourceComesFromTheOriginalSite() {
    assertThat(
            SpaceSearchService.source(
                "https://www.k-startup.go.kr/web/contents/bizpbanc-ongoing.do?schM=view&pbancSn=179465"))
        .isEqualTo("KSTARTUP");
    assertThat(
            SpaceSearchService.source(
                "https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=PBLN_1"))
        .isEqualTo("BIZINFO");
    assertThat(SpaceSearchService.source("https://example.org")).isNull();
    assertThat(SpaceSearchService.source(null)).isNull();
  }

  @Test
  void sameRecruitmentFromTwoSitesShowsOnce() {
    var bizinfo = policy("00000000-0000-0000-0000-000000000011", "BIZINFO", "[서울] 관악S밸리 입주기업 모집");
    var kstartup = policy("00000000-0000-0000-0000-000000000012", "KSTARTUP", "서울 관악S밸리 입주기업 모집");
    var other = policy("00000000-0000-0000-0000-000000000013", "BIZINFO", "동국대 창업보육센터 입주기업 모집");

    // 글자·숫자만 같으면 같은 모집이에요. K-Startup을 남기고 처음 순서는 그대로
    assertThat(SpaceSearchService.withoutDuplicates(List.of(bizinfo, other, kstartup)))
        .containsExactly(other, kstartup);
  }

  @Test
  void sameProgramWithDifferentTitlesIsFoundByCoreNameAndDeadline() {
    LocalDate end = LocalDate.parse("2026-11-03");
    String kstartup = "<2026년 시제품 고도화 바우처 지원 프로그램> 참여 기업 모집 (~11.3.14시)";
    String bizinfo = "[충북] 청주시 2026년 시제품 고도화 바우처 지원 프로그램 참여 기업 모집 공고";
    assertThat(SpaceSearchService.sameProgram(kstartup, end, bizinfo, end)).isTrue();
    // 마감일이 다르면 다른 회차예요
    assertThat(SpaceSearchService.sameProgram(kstartup, end, bizinfo, end.plusDays(7))).isFalse();
    // 짧은 흔한 이름끼리는 포함 관계여도 묶지 않아요
    assertThat(SpaceSearchService.sameProgram("창업 지원", end, "서울 창업 지원 사업", end)).isFalse();
  }

  @Test
  void searchShowsJudgedSpacesInOrderPageByPage() {
    givenSpaces();

    SpaceSearchResponse first =
        spaces.search(new SpaceSearchRequest(null, null, null, null, null, 2));

    // 같은 모집(K-Startup·기업마당)은 하나만 세고, 지원 불가는 개수에만 들어가요
    assertThat(first.counts()).isEqualTo(new SpaceSearchResponse.Counts(1, 2, 1));
    assertThat(first.typeCounts())
        .containsExactly(
            entry("STARTUP_SPACE", 3), entry("SHOP_RENTAL", 1), entry("MEETING_ROOM", 0));
    // 지원 가능 → 확인 필요(마감 임박순)
    assertThat(first.items()).extracting(SpaceSearchResponse.Item::id).containsExactly(SHOP, BUSAN);
    assertThat(first.hasNext()).isTrue();
    SpaceSearchResponse.Item shop = first.items().getFirst();
    assertThat(shop.spaceType()).isEqualTo("SHOP_RENTAL");
    assertThat(shop.provider()).isEqualTo("서울주택도시공사");
    assertThat(shop.regionName()).isEqualTo("서울 성동구");
    assertThat(shop.status()).isEqualTo("APPLYING");
    assertThat(shop.dday()).isEqualTo(11);
    assertThat(shop.tags()).containsExactly("역세권");
    assertThat(shop.source()).isNull();
    // 공고 목록 정보에서 종류를 모르면 창업 공간이에요
    assertThat(first.items().get(1).spaceType()).isEqualTo("STARTUP_SPACE");

    SpaceSearchResponse second =
        spaces.search(new SpaceSearchRequest(null, null, null, null, first.nextCursor(), 2));

    assertThat(second.items()).extracting(SpaceSearchResponse.Item::id).containsExactly(KSTARTUP);
    assertThat(second.hasNext()).isFalse();
    SpaceSearchResponse.Item policy = second.items().getFirst();
    assertThat(policy.policy()).isTrue();
    assertThat(policy.source()).isEqualTo("KSTARTUP");
    assertThat(policy.spaceType()).isEqualTo("STARTUP_SPACE");
    assertThat(policy.organization()).isEqualTo("경기과학기술대학교 창업보육센터");
    assertThat(policy.status()).isEqualTo("APPLYING"); // 모집 정책은 기간으로 정해요
    assertThat(policy.dday()).isEqualTo(19);
    assertThat(policy.applyNote()).isEqualTo("입주 심사 후 개별 안내");
  }

  @Test
  void searchFiltersByRegionTypeAndKeyword() {
    givenSpaces();

    SpaceSearchResponse seoulStartup =
        spaces.search(
            new SpaceSearchRequest(
                new SpaceSearchRequest.Filters(List.of("STARTUP_SPACE"), List.of("11"), null),
                null,
                "DEADLINE",
                true,
                null,
                null));

    // 서울만 남아요 (경기·부산 빠짐). 종류별 개수는 종류로 거르기 전이고, 지원 불가도 보여줘요
    assertThat(seoulStartup.typeCounts())
        .containsEntry("SHOP_RENTAL", 1)
        .containsEntry("STARTUP_SPACE", 1);
    assertThat(seoulStartup.counts()).isEqualTo(new SpaceSearchResponse.Counts(0, 0, 1));
    assertThat(seoulStartup.items()).extracting(SpaceSearchResponse.Item::id).containsExactly(MAPO);

    SpaceSearchResponse byName =
        spaces.search(
            new SpaceSearchRequest(
                new SpaceSearchRequest.Filters(null, null, "경기과학기술대 창업보육센터"),
                null,
                null,
                null,
                null,
                null));

    assertThat(byName.items()).extracting(SpaceSearchResponse.Item::id).containsExactly(KSTARTUP);
  }

  @Test
  void evaluateAddsTheNoticeToTheJudgment() {
    JudgmentResult judgment = judgment();
    when(matches.judgeBusinessSpace(KSTARTUP, null))
        .thenReturn(
            Optional.of(
                new MatchQueryService.OneJudgment(
                    notice(KSTARTUP, true, "2026-11-02", "https://www.k-startup.go.kr/view"),
                    judgment)));
    when(notices.policyInfos(List.of(KSTARTUP))).thenReturn(Map.of(KSTARTUP, GTEC));

    SpaceEvaluationResponse policy = spaces.evaluate(KSTARTUP, null);

    assertThat(policy.policy()).isTrue();
    assertThat(policy.source()).isEqualTo("KSTARTUP");
    assertThat(policy.status()).isEqualTo("UPCOMING"); // 접수 시작 전
    assertThat(policy.dday()).isEqualTo(19);
    assertThat(policy.info()).isEqualTo(GTEC);
    assertThat(policy.judgment()).isSameAs(judgment);
  }

  @Test
  void evaluateOfANoticeHasNoPolicyInfo() {
    when(matches.judgeBusinessSpace(SHOP, null))
        .thenReturn(
            Optional.of(
                new MatchQueryService.OneJudgment(notice(SHOP, false, null, null), judgment())));

    SpaceEvaluationResponse notice = spaces.evaluate(SHOP, null);

    assertThat(notice.source()).isNull();
    assertThat(notice.info()).isNull();
    assertThat(notice.status()).isEqualTo("APPLYING");
  }

  @Test
  void evaluateOfAClosedOrUnknownSpaceIsNotFound() {
    assertThatThrownBy(() -> spaces.evaluate(BUSAN, null))
        .isInstanceOfSatisfying(
            CustomException.class,
            e -> assertThat(e.errorCode()).isEqualTo(ErrorCode.NOTICE_NOT_FOUND));
  }

  /**
   * 열린 사업공간 5개: 성동 공공 상가(지원 가능), 경기과학기술대 입주 모집(K-Startup·기업마당에 같이 올라온 정책, 확인 필요), 마포 창업 공간(지원 불가),
   * 부산 창업 공간(확인 필요, 공고 목록에 종류 없음).
   */
  private void givenSpaces() {
    String gtec = "경기과학기술대학교 창업보육센터 입주기업 모집";
    when(matches.judgeBusinessSpaceAll(any()))
        .thenReturn(
            List.of(
                judged(
                    SHOP,
                    null,
                    "성수 공공 상가 입주자 모집",
                    "2026-11-10",
                    "1120011500",
                    Eligibility.ELIGIBLE),
                judged(
                    BIZINFO,
                    "https://www.bizinfo.go.kr/view",
                    "[경기] " + gtec,
                    "2026-11-18",
                    "4139000000",
                    Eligibility.NEEDS_INPUT),
                judged(
                    KSTARTUP,
                    "https://www.k-startup.go.kr/view",
                    gtec,
                    "2026-11-18",
                    "4139000000",
                    Eligibility.NEEDS_INPUT),
                judged(
                    MAPO,
                    null,
                    "마포 창업 공간 입주기업 모집",
                    "2026-11-01",
                    "1144000000",
                    Eligibility.INELIGIBLE),
                judged(
                    BUSAN,
                    null,
                    "부산 창업 공간 입주기업 모집",
                    "2026-11-05",
                    "2611000000",
                    Eligibility.NEEDS_INPUT)));
    when(notices.searchCandidates(
            eq("BUSINESS_SPACE"), any(), any(), any(), any(), any(), any(), anyInt()))
        .thenReturn(
            List.of(
                candidate(SHOP, "SHOP_RENTAL", "서울주택도시공사", "서울 성동구", List.of("역세권")),
                candidate(MAPO, "STARTUP_SPACE", "서울경제진흥원", "서울 마포구", List.of()),
                candidate(BUSAN, null, "부산경제진흥원", "부산 해운대구", List.of())));
    when(notices.policyInfos(any())).thenReturn(Map.of(KSTARTUP, GTEC, BIZINFO, GTEC));
  }

  /** 판정된 공간 하나. 원문 주소가 있으면 모집 정책이에요. */
  private static MatchResult.Item judged(
      UUID id, String detailUrl, String title, String applyEnd, String region, Eligibility status) {
    return new MatchResult.Item(
        id,
        detailUrl != null,
        1,
        title,
        detailUrl,
        List.of(region),
        LocalDate.parse("2026-10-27"),
        LocalDate.parse(applyEnd),
        status,
        null,
        null,
        List.of(),
        List.of());
  }

  private static NoticeQueryService.Candidate candidate(
      UUID id, String noticeType, String provider, String regionName, List<String> tags) {
    return new NoticeQueryService.Candidate(
        id,
        "BUSINESS_SPACE",
        "공간",
        provider,
        noticeType,
        null,
        regionName,
        "APPLYING",
        null,
        null,
        null,
        null,
        null,
        null,
        1,
        null,
        tags);
  }

  private static NoticeCandidate notice(UUID id, boolean policy, String applyStart, String url) {
    return new NoticeCandidate(
        id,
        policy,
        1,
        "공간",
        applyStart == null ? null : LocalDate.parse(applyStart),
        LocalDate.parse("2026-11-18"),
        List.of("4139000000"),
        null,
        url);
  }

  private static JudgmentResult judgment() {
    return new JudgmentResult(
        "BUSINESS_SPACE",
        Eligibility.NEEDS_INPUT,
        null,
        LocalDate.parse("2026-10-27"),
        List.of(),
        List.of(),
        List.of(),
        List.of(),
        List.of());
  }

  private static SpaceSearchResponse.Item policy(String id, String source, String title) {
    return new SpaceSearchResponse.Item(
        UUID.fromString(id),
        true,
        source,
        "STARTUP_SPACE",
        title,
        null,
        null,
        null,
        List.of(),
        "APPLYING",
        null,
        null,
        null,
        Eligibility.NEEDS_INPUT,
        null,
        List.of(),
        List.of(),
        null,
        List.of(),
        null);
  }

  private static SpaceSearchResponse.Item item(String id, Eligibility overall, String applyEnd) {
    return new SpaceSearchResponse.Item(
        UUID.fromString(id),
        false,
        null,
        "STARTUP_SPACE",
        "공간",
        null,
        null,
        null,
        List.of(),
        "APPLYING",
        null,
        applyEnd == null ? null : LocalDate.parse(applyEnd),
        null,
        overall,
        null,
        List.of(),
        List.of(),
        null,
        List.of(),
        null);
  }
}
