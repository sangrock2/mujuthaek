package kr.mujuthaek.api.eligibility.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.assertj.core.api.Assertions.entry;
import static org.mockito.ArgumentMatchers.any;
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
import kr.mujuthaek.api.eligibility.dto.request.SupportSearchRequest;
import kr.mujuthaek.api.eligibility.dto.response.SupportEvaluationResponse;
import kr.mujuthaek.api.eligibility.dto.response.SupportSearchResponse;
import kr.mujuthaek.api.eligibility.model.JudgmentResult;
import kr.mujuthaek.api.eligibility.model.MatchResult;
import kr.mujuthaek.api.eligibility.model.NoticeCandidate;
import kr.mujuthaek.api.eligibility.rule.Eligibility;
import kr.mujuthaek.api.notice.service.NoticeQueryService;
import org.junit.jupiter.api.Test;

/**
 * 사업 지원 맞춤 목록·상세. 지원 종류 나누기·같은 사업 하나만, 목록(거르기·개수·페이지)과 상세 응답을 봐요. 판정과 출처 안내는 가짜로 넣어요. 판정 자체는 {@link
 * MatchQueryServiceTest}에서 봐요.
 */
class SupportSearchServiceTest {

  private static final UUID KSTARTUP = UUID.fromString("00000000-0000-0000-0000-000000000031");
  private static final UUID BIZINFO = UUID.fromString("00000000-0000-0000-0000-000000000032");
  private static final UUID SEOUL_LOAN = UUID.fromString("00000000-0000-0000-0000-000000000033");
  private static final UUID BUSAN_TAX = UUID.fromString("00000000-0000-0000-0000-000000000034");
  private static final NoticeQueryService.PolicyInfo PACKAGE =
      new NoticeQueryService.PolicyInfo(
          "사업화", null, "창업진흥원", null, null, null, null, "최대 1억원", null);
  private static final NoticeQueryService.PolicyInfo LOAN =
      new NoticeQueryService.PolicyInfo("융자", null, "서울신용보증재단", null, null, null, null, null, null);

  private final MatchQueryService matches = mock(MatchQueryService.class);
  private final NoticeQueryService notices = mock(NoticeQueryService.class);
  // 오늘은 2026-10-30 (한국 시간)
  private final SupportSearchService supports =
      new SupportSearchService(
          matches,
          notices,
          Clock.fixed(Instant.parse("2026-10-30T01:00:00Z"), ZoneId.of("Asia/Seoul")));

  @Test
  void subFieldComesFromTheName() {
    assertThat(SupportSearchService.subField(null, "2026년 용산구 청년기업 융자지원사업")).isEqualTo("LOAN");
    assertThat(SupportSearchService.subField(null, "청년 창업 정책자금")).isEqualTo("LOAN");
    assertThat(SupportSearchService.subField(null, "청년 창업 세액감면 안내")).isEqualTo("TAX");
    assertThat(SupportSearchService.subField(null, "2026년 예비창업패키지 사업화 자금 지원")).isEqualTo("FUND");
    assertThat(SupportSearchService.subField(null, "창업보육센터 입주기업 지원")).isEqualTo("FUND");
    assertThat(SupportSearchService.subField(null, null)).isEqualTo("FUND");
    // 출처의 지원 분야가 있으면 그걸로 (이름에 없어도)
    assertThat(SupportSearchService.subField("융자", "2026 청년 창업 지원")).isEqualTo("LOAN");
    assertThat(SupportSearchService.subField("사업화", "2026 청년 창업 지원")).isEqualTo("FUND");
  }

  @Test
  void sameProgramFromTwoSitesShowsOnce() {
    var bizinfo = item("00000000-0000-0000-0000-000000000021", "BIZINFO", "[서울] 2026 웰컴 투 팁스 모집");
    var other = item("00000000-0000-0000-0000-000000000022", "BIZINFO", "김해시 창업 지원금");
    var kstartup = item("00000000-0000-0000-0000-000000000023", "KSTARTUP", "서울 2026 웰컴 투 팁스 모집");

    assertThat(SupportSearchService.withoutDuplicates(List.of(bizinfo, other, kstartup)))
        .containsExactly(other, kstartup);
  }

  @Test
  void searchShowsJudgedProgramsInOrderPageByPage() {
    givenPrograms();

    SupportSearchResponse first =
        supports.search(new SupportSearchRequest(null, null, null, null, null, 1));

    // 같은 사업(K-Startup·기업마당)은 하나만 세고, 지원 불가는 개수에만 들어가요
    assertThat(first.counts()).isEqualTo(new SupportSearchResponse.Counts(1, 1, 1));
    assertThat(first.subFieldCounts())
        .containsExactly(entry("FUND", 1), entry("LOAN", 1), entry("TAX", 1));
    assertThat(first.items()).extracting(SupportSearchResponse.Item::id).containsExactly(KSTARTUP);
    assertThat(first.hasNext()).isTrue();
    SupportSearchResponse.Item pack = first.items().getFirst();
    assertThat(pack.source()).isEqualTo("KSTARTUP");
    assertThat(pack.subField()).isEqualTo("FUND");
    assertThat(pack.supportArea()).isEqualTo("사업화");
    assertThat(pack.organization()).isEqualTo("창업진흥원");
    assertThat(pack.amountText()).isEqualTo("최대 1억원");
    assertThat(pack.status()).isEqualTo("APPLYING");
    assertThat(pack.dday()).isEqualTo(21);

    SupportSearchResponse second =
        supports.search(new SupportSearchRequest(null, null, null, null, first.nextCursor(), 1));

    assertThat(second.items())
        .extracting(SupportSearchResponse.Item::id)
        .containsExactly(SEOUL_LOAN);
    assertThat(second.items().getFirst().subField()).isEqualTo("LOAN");
    assertThat(second.hasNext()).isFalse();
  }

  @Test
  void searchFiltersByRegionSubFieldAndKeyword() {
    givenPrograms();

    SupportSearchResponse busanTax =
        supports.search(
            new SupportSearchRequest(
                new SupportSearchRequest.Filters(List.of("TAX"), List.of("26"), null),
                null,
                "DEADLINE",
                true,
                null,
                null));

    // 부산과 전국 사업만 남아요 (서울 빠짐). 종류별 개수는 종류로 거르기 전이고, 지원 불가도 보여줘요
    assertThat(busanTax.subFieldCounts()).containsEntry("FUND", 1).containsEntry("LOAN", 0);
    assertThat(busanTax.counts()).isEqualTo(new SupportSearchResponse.Counts(0, 0, 1));
    assertThat(busanTax.items())
        .extracting(SupportSearchResponse.Item::id)
        .containsExactly(BUSAN_TAX);
    SupportSearchResponse.Item tax = busanTax.items().getFirst();
    assertThat(tax.status()).isEqualTo("ALWAYS"); // 마감 없는 상시 사업
    assertThat(tax.dday()).isNull();
    assertThat(tax.source()).isNull();

    SupportSearchResponse byOrganization =
        supports.search(
            new SupportSearchRequest(
                new SupportSearchRequest.Filters(null, null, "창업진흥원"),
                null,
                null,
                null,
                null,
                null));

    assertThat(byOrganization.items())
        .extracting(SupportSearchResponse.Item::id)
        .containsExactly(KSTARTUP);
  }

  @Test
  void evaluateAddsTheSourceGuideToTheJudgment() {
    JudgmentResult judgment = judgment();
    when(matches.judgeStartupSupport(SEOUL_LOAN, null))
        .thenReturn(
            Optional.of(
                new MatchQueryService.OneJudgment(
                    program(SEOUL_LOAN, "2026 청년 창업 지원", "https://www.bizinfo.go.kr/view"),
                    judgment)));
    when(notices.policyInfos(List.of(SEOUL_LOAN))).thenReturn(Map.of(SEOUL_LOAN, LOAN));

    SupportEvaluationResponse loan = supports.evaluate(SEOUL_LOAN, null);

    assertThat(loan.source()).isEqualTo("BIZINFO");
    assertThat(loan.subField()).isEqualTo("LOAN"); // 이름에 없어도 출처의 지원 분야(융자)로
    assertThat(loan.status()).isEqualTo("UPCOMING"); // 접수 시작 전
    assertThat(loan.dday()).isEqualTo(6);
    assertThat(loan.info()).isEqualTo(LOAN);
    assertThat(loan.judgment()).isSameAs(judgment);
  }

  @Test
  void evaluateWithoutASourceGuideUsesTheName() {
    when(matches.judgeStartupSupport(BUSAN_TAX, null))
        .thenReturn(
            Optional.of(
                new MatchQueryService.OneJudgment(
                    program(BUSAN_TAX, "부산 창업기업 세액감면 안내", null), judgment())));

    SupportEvaluationResponse tax = supports.evaluate(BUSAN_TAX, null);

    assertThat(tax.subField()).isEqualTo("TAX");
    assertThat(tax.info()).isNull();
    assertThat(tax.source()).isNull();
  }

  @Test
  void evaluateOfAClosedOrUnknownProgramIsNotFound() {
    assertThatThrownBy(() -> supports.evaluate(KSTARTUP, null))
        .isInstanceOfSatisfying(
            CustomException.class,
            e -> assertThat(e.errorCode()).isEqualTo(ErrorCode.NOTICE_NOT_FOUND));
  }

  /**
   * 열린 사업 4개: 예비창업패키지(K-Startup·기업마당에 같이 올라온 전국 사업, 지원 가능), 서울 청년 창업 정책자금(확인 필요), 부산 세액감면(상시, 지원
   * 불가).
   */
  private void givenPrograms() {
    String pack = "2026년 예비창업패키지 예비창업자 모집";
    when(matches.judgeStartupSupportAll(any()))
        .thenReturn(
            List.of(
                judged(
                    BIZINFO,
                    "https://www.bizinfo.go.kr/view",
                    "[전국] " + pack,
                    "2026-11-20",
                    List.of(),
                    Eligibility.ELIGIBLE),
                judged(
                    KSTARTUP,
                    "https://www.k-startup.go.kr/view",
                    pack,
                    "2026-11-20",
                    List.of(),
                    Eligibility.ELIGIBLE),
                judged(
                    SEOUL_LOAN,
                    "https://www.bizinfo.go.kr/view",
                    "서울 청년 창업 정책자금 융자 지원",
                    "2026-11-05",
                    List.of("1100000000"),
                    Eligibility.NEEDS_INPUT),
                judged(
                    BUSAN_TAX,
                    null,
                    "부산 창업기업 세액감면 안내",
                    null,
                    List.of("2600000000"),
                    Eligibility.INELIGIBLE)));
    when(notices.policyInfos(any())).thenReturn(Map.of(KSTARTUP, PACKAGE, BIZINFO, PACKAGE));
  }

  private static MatchResult.Item judged(
      UUID id,
      String detailUrl,
      String title,
      String applyEnd,
      List<String> regions,
      Eligibility status) {
    return new MatchResult.Item(
        id,
        true,
        1,
        title,
        detailUrl,
        regions,
        LocalDate.parse("2026-10-20"),
        applyEnd == null ? null : LocalDate.parse(applyEnd),
        status,
        null,
        null,
        List.of(),
        List.of());
  }

  private static NoticeCandidate program(UUID id, String title, String url) {
    return new NoticeCandidate(
        id,
        true,
        1,
        title,
        LocalDate.parse("2026-11-01"),
        LocalDate.parse("2026-11-05"),
        List.of(),
        null,
        url);
  }

  private static JudgmentResult judgment() {
    return new JudgmentResult(
        "STARTUP_SUPPORT",
        Eligibility.NEEDS_INPUT,
        null,
        null,
        List.of(),
        List.of(),
        List.of(),
        List.of(),
        List.of());
  }

  private static SupportSearchResponse.Item item(String id, String source, String title) {
    return new SupportSearchResponse.Item(
        UUID.fromString(id),
        source,
        "FUND",
        null,
        null,
        null,
        title,
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
        null);
  }
}
