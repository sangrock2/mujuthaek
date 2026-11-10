package kr.mujuthaek.api.notice;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.Mockito.doThrow;

import java.io.IOException;
import java.io.InputStream;
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.util.EnumSet;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import kr.mujuthaek.api.TestcontainersConfiguration;
import kr.mujuthaek.api.common.event.AreaScoresCalculated;
import kr.mujuthaek.api.common.event.NoticeClosed;
import kr.mujuthaek.api.common.event.NoticeLocationsChanged;
import kr.mujuthaek.api.common.event.NoticePublished;
import kr.mujuthaek.api.common.event.NoticeUpdated;
import kr.mujuthaek.api.common.event.PolicyPublished;
import kr.mujuthaek.api.common.event.PolicyUpdated;
import kr.mujuthaek.api.notice.domain.DuplicateRule;
import kr.mujuthaek.api.notice.domain.IngestionOutcome;
import kr.mujuthaek.api.notice.dto.request.NoticeListFilter;
import kr.mujuthaek.api.notice.dto.response.NoticeDetailResponse;
import kr.mujuthaek.api.notice.dto.response.NoticeSummaryResponse;
import kr.mujuthaek.api.notice.mapper.ExtractionEvent;
import kr.mujuthaek.api.notice.repository.ExtractionResultRepository;
import kr.mujuthaek.api.notice.service.NoticeField;
import kr.mujuthaek.api.notice.service.NoticeForJudgment;
import kr.mujuthaek.api.notice.service.NoticeQueryService;
import kr.mujuthaek.api.notice.service.PolicySummary;
import kr.mujuthaek.api.notice.service.ProgramForJudgment;
import kr.mujuthaek.api.notice.service.internal.NoticeAreaScoreService;
import kr.mujuthaek.api.notice.service.internal.NoticeBackfillService;
import kr.mujuthaek.api.notice.service.internal.NoticeIngestionService;
import kr.mujuthaek.api.notice.service.internal.NoticeMergeService;
import kr.mujuthaek.api.notice.service.internal.NoticeStatusService;
import kr.mujuthaek.api.notice.service.internal.PolicyDuplicateService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.Primary;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;
import org.springframework.test.context.event.ApplicationEvents;
import org.springframework.test.context.event.RecordApplicationEvents;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;
import tools.jackson.databind.node.ArrayNode;
import tools.jackson.databind.node.ObjectNode;

/** 실제 extraction 결과(서리풀 공고, PARTIALLY_PASSED)로 수신·저장·조회를 확인해요. AI 호출은 없어요. */
@SpringBootTest(
    properties = {
      "spring.rabbitmq.listener.simple.auto-startup=false",
      "notice.status-refresh.enabled=false" // 재계산은 테스트에서 직접 불러요
    })
@Import({TestcontainersConfiguration.class, NoticeIngestionIntegrationTest.FixedClock.class})
@RecordApplicationEvents
class NoticeIngestionIntegrationTest {

  /** 기본 2026-10-19 09:00 (한국). 서리풀 공고 접수는 10/26~10/30이에요. 테스트에서 시각을 옮길 수 있어요. */
  static final Instant START = Instant.parse("2026-10-19T00:00:00Z");

  static final ZoneId KOREA = ZoneId.of("Asia/Seoul");

  static final class MovableClock extends Clock {
    private volatile Instant now = START;

    void set(String koreaDateTime) {
      now = LocalDateTime.parse(koreaDateTime).atZone(KOREA).toInstant();
    }

    @Override
    public ZoneId getZone() {
      return KOREA;
    }

    @Override
    public Clock withZone(ZoneId zone) {
      return this;
    }

    @Override
    public Instant instant() {
      return now;
    }
  }

  @TestConfiguration(proxyBeanMethods = false)
  static class FixedClock {
    @Bean
    @Primary
    MovableClock movableClock() {
      return new MovableClock();
    }
  }

  @Autowired NoticeIngestionService ingestion;
  @Autowired NoticeQueryService query;
  @Autowired JdbcClient jdbc;
  @Autowired JsonMapper json;
  @Autowired ApplicationEvents events;
  @Autowired MovableClock clock;
  @Autowired NoticeStatusService status;
  @Autowired NoticeMergeService merges;
  @Autowired NoticeAreaScoreService areaScores;
  @Autowired NoticeBackfillService backfill;
  @Autowired PolicyDuplicateService duplicates;
  @MockitoSpyBean ExtractionResultRepository results;

  @BeforeEach
  void clean() {
    clock.now = START;
    jdbc.sql(
            "truncate notice.notice_reports, notice.notice_versions, notice.notice_posts,"
                + " notice.notice_follow_ups,"
                + " notice.notice_regions, notice.notice_source_heads,"
                + " notice.notice_duplicate_candidates, notice.notice_area_scores, notice.notices,"
                + " notice.extraction_results, notice.policy_duplicate_candidates, notice.policy_judgments,"
                + " common.processed_events")
        .update();
  }

  // ---------- 수신·공개 ----------

  @Test
  void 부분_게시_결과를_공개하고_NoticePublished를_보낸다() {
    assertThat(ingestion.apply(body(fixture()))).isEqualTo(IngestionOutcome.PUBLISHED);

    UUID id = onlyNotice();
    NoticeDetailResponse detail = query.detail(id);
    assertThat(detail.header().title())
        .isEqualTo(fixture().path("payload").path("title").asString());
    assertThat(detail.header().regionCode()).isEqualTo("11650");
    assertThat(detail.version()).isEqualTo(1);
    assertThat(events.stream(NoticePublished.class))
        .singleElement()
        .satisfies(
            e -> {
              assertThat(e.noticeId()).isEqualTo(id);
              assertThat(e.field()).isEqualTo("HOUSING");
              assertThat(e.regionCode()).isEqualTo("11650");
              assertThat(e.reprocess()).isFalse();
            });
  }

  @Test
  void 상세의_조건_일정_가격에_근거_원문과_쪽을_붙이고_보류한_조건의_근거는_비운다() {
    ObjectNode event = fixture();
    // 실제 결과의 근거는 모두 글자 범위(TEXT_RANGE)라 쪽이 없어요. 쪽을 보려고 조건 근거 하나를 첨부 PDF 쪽 근거로 바꿔요
    for (JsonNode e : event.path("payload").path("notice").path("evidence")) {
      if (e.path("id").asString().equals("ev-22")) {
        ((ObjectNode) e).put("sourceId", "file-1");
        ((ObjectNode) e)
            .putObject("locator")
            .put("kind", "PDF_PAGE")
            .put("page", 3)
            .put("printedPage", "- 2 -");
      }
    }
    ingestion.apply(body(event));

    UUID id = onlyNotice();
    NoticeDetailResponse detail = query.detail(id);
    NoticeDetailResponse.Condition arts = condition(detail, "eligibility-arts-proof");
    assertThat(arts.evidence())
        .singleElement()
        .satisfies(
            e -> {
              assertThat(e.quote()).startsWith("가.「문화예술진흥법」에 따른 문화예술 분야에 종사하며");
              assertThat(e.page()).isEqualTo(3);
              assertThat(e.printedPage()).isEqualTo("- 2 -");
              assertThat(e.documentName()).isEqualTo("311521_1.pdf");
            });
    // 글자 범위 근거는 쪽 없이 인용과 문서 이름만
    assertThat(condition(detail, "eligibility-age").evidence())
        .singleElement()
        .satisfies(
            e -> {
              assertThat(e.quote()).isNotBlank();
              assertThat(e.page()).isNull();
              assertThat(e.documentName()).isEqualTo("첨부 PDF에서 읽은 글자 (쪽·표 구분)");
            });
    // 보류한 조건(/eligibility/4)은 확인 필요로 두고 근거를 보여 주지 않아요
    NoticeDetailResponse.Condition held =
        condition(detail, "eligibility-income-assets-alternative");
    assertThat(held.inReview()).isTrue();
    assertThat(held.evidence()).isEmpty();

    assertThat(detail.schedules())
        .filteredOn(s -> "schedule-announcement".equals(s.id()))
        .singleElement()
        .satisfies(
            s ->
                assertThat(s.evidence())
                    .singleElement()
                    .satisfies(e -> assertThat(e.quote()).contains("모집공고", "10.30.")));
    assertThat(detail.schedules()).allSatisfy(s -> assertThat(s.evidence()).isNotEmpty());

    // 보증금·월임대료가 같은 표 행을 근거로 하면 한 번만
    assertThat(query.units(id, null, null, null).items().getFirst().evidence())
        .singleElement()
        .satisfies(e -> assertThat(e.quote()).contains("31,600,000", "411,700"));
  }

  @Test
  void 글자_범위_근거에_실린_PDF_쪽_번호도_상세에_보인다() {
    ObjectNode event = fixture();
    // 추출이 PDF 글자 근거의 글자 범위에 쪽 번호를 실은 경우(요구 2-07): 나이 조건 근거(ev-23)에 쪽을 실어요
    for (JsonNode e : event.path("payload").path("notice").path("evidence")) {
      if (e.path("id").asString().equals("ev-23")) {
        ((ObjectNode) e.path("locator")).put("page", 2);
      }
    }
    ingestion.apply(body(event));

    NoticeDetailResponse detail = query.detail(onlyNotice());
    assertThat(condition(detail, "eligibility-age").evidence())
        .singleElement()
        .satisfies(
            e -> {
              assertThat(e.page()).isEqualTo(2);
              assertThat(e.printedPage()).isNull();
              assertThat(e.documentName()).isEqualTo("첨부 PDF에서 읽은 글자 (쪽·표 구분)");
            });
  }

  private static NoticeDetailResponse.Condition condition(NoticeDetailResponse detail, String id) {
    return detail.conditions().stream().filter(c -> id.equals(c.id())).findFirst().orElseThrow();
  }

  @Test
  void 같은_이벤트가_동시에_와도_한_번만_처리하고_나머지는_예외_없이_DUPLICATE다() throws Exception {
    // 2026-11-01 동시성 시험: 100개 동시에 9개가 처리 기록 기본 키에서 부딪혀 예외(→ 재시도·실패 큐)였어요
    String body = body(fixture());
    int threads = 20;
    var pool = java.util.concurrent.Executors.newFixedThreadPool(threads);
    var ready = new java.util.concurrent.CountDownLatch(threads);
    var go = new java.util.concurrent.CountDownLatch(1);
    List<java.util.concurrent.Future<IngestionOutcome>> results = new java.util.ArrayList<>();
    for (int i = 0; i < threads; i++) {
      results.add(
          pool.submit(
              () -> {
                ready.countDown();
                go.await();
                return ingestion.apply(body);
              }));
    }
    ready.await();
    go.countDown();
    List<IngestionOutcome> outcomes = new java.util.ArrayList<>();
    for (var f : results) {
      outcomes.add(f.get(60, java.util.concurrent.TimeUnit.SECONDS)); // 예외면 여기서 실패해요
    }
    pool.shutdown();

    assertThat(outcomes).filteredOn(o -> o == IngestionOutcome.DUPLICATE).hasSize(threads - 1);
    assertThat(count("notice.notices")).isEqualTo(1);
    assertThat(count("notice.notice_versions")).isEqualTo(1);
    assertThat(count("notice.extraction_results")).isEqualTo(1);
  }

  @Test
  void 같은_이벤트를_두_번_받아도_공고와_버전은_하나다() {
    ObjectNode event = fixture();
    ingestion.apply(body(event));

    assertThat(ingestion.apply(body(event))).isEqualTo(IngestionOutcome.DUPLICATE);
    assertThat(count("notice.notices")).isEqualTo(1);
    assertThat(count("notice.notice_versions")).isEqualTo(1);
    assertThat(count("notice.extraction_results")).isEqualTo(1);
    assertThat(events.stream(NoticePublished.class)).hasSize(1);
  }

  @Test
  void 검수_대기_결과는_공개하지_않고_기록만_남긴다() {
    assertThat(ingestion.apply(body(withStatus(fixture(), "IN_REVIEW"))))
        .isEqualTo(IngestionOutcome.HELD);

    assertThat(count("notice.notices")).isZero();
    assertThat(outcomes()).containsExactly("HELD:IN_REVIEW");
    assertThat(events.stream(NoticePublished.class)).isEmpty();
  }

  @Test
  void 같은_원본_버전이_검수_대기로_다시_와도_공개_중인_내용은_그대로다() {
    ingestion.apply(body(fixture()));
    ObjectNode inReview = withStatus(fixture(), "IN_REVIEW");
    inReview.put("eventId", UUID.randomUUID().toString());
    ((ObjectNode) inReview.path("payload")).put("summary", "검수 전 요약");

    assertThat(ingestion.apply(body(inReview))).isEqualTo(IngestionOutcome.HELD);
    assertThat(count("notice.notice_versions")).isEqualTo(1);
    assertThat(query.detail(onlyNotice()).summary().summaryText()).isNotEqualTo("검수 전 요약");
  }

  @Test
  void 상세가_없는_결과는_공개하지_않는다() {
    ObjectNode event = withStatus(fixture(), "IN_REVIEW");
    ((ObjectNode) event.path("payload")).remove("notice");

    assertThat(ingestion.apply(body(event))).isEqualTo(IngestionOutcome.HELD);
    assertThat(outcomes()).containsExactly("HELD:DETAIL_MISSING");
  }

  @Test
  void 내용이_같은_새_이벤트는_새_버전을_만들지_않는다() {
    ingestion.apply(body(fixture()));
    ObjectNode again = fixture();
    again.put("eventId", UUID.randomUUID().toString());
    ((ObjectNode) again.path("payload").path("notice").path("input"))
        .put("eventId", UUID.randomUUID().toString());

    assertThat(ingestion.apply(body(again))).isEqualTo(IngestionOutcome.NO_CHANGE);
    assertThat(count("notice.notice_versions")).isEqualTo(1);
  }

  @Test
  void 근거_위치_같은_보이지_않는_부분만_바뀌면_새_버전을_만들지_않는다() {
    ingestion.apply(body(fixture()));
    ObjectNode next = withRawVersion(fixture(), 2); // 원본 버전 기록만 다르고 보이는 내용은 같음
    next.put("eventId", UUID.randomUUID().toString());

    assertThat(ingestion.apply(body(next))).isEqualTo(IngestionOutcome.NO_CHANGE);
    assertThat(outcomes()).contains("NO_CHANGE:NO_VISIBLE_CHANGE");
    assertThat(count("notice.notice_versions")).isEqualTo(1);
    assertThat(events.stream(NoticeUpdated.class)).isEmpty();
  }

  @Test
  void 내용이_바뀐_새_원본_버전은_새_버전으로_교체하고_NoticeUpdated를_보낸다() {
    ingestion.apply(body(fixture()));
    ObjectNode changed = withRawVersion(fixture(), 2);
    changed.put("eventId", UUID.randomUUID().toString());
    ((ObjectNode) changed.path("payload")).put("title", "바뀐 제목");
    ((ObjectNode) changed.path("payload").path("notice").path("notice")).put("title", "바뀐 제목");

    assertThat(ingestion.apply(body(changed))).isEqualTo(IngestionOutcome.NEW_VERSION);

    NoticeDetailResponse detail = query.detail(onlyNotice());
    assertThat(detail.header().title()).isEqualTo("바뀐 제목");
    assertThat(detail.version()).isEqualTo(2);
    assertThat(events.stream(NoticeUpdated.class))
        .singleElement()
        .satisfies(
            e -> {
              assertThat(e.field()).isEqualTo("HOUSING");
              assertThat(e.changedFields()).containsExactly("notice");
            });
  }

  @Test
  void 낮은_원본_버전은_STALE로_기록만_한다() {
    ObjectNode newer = withRawVersion(fixture(), 3);
    ingestion.apply(body(newer));
    ObjectNode older = withRawVersion(fixture(), 2);
    older.put("eventId", UUID.randomUUID().toString());

    assertThat(ingestion.apply(body(older))).isEqualTo(IngestionOutcome.STALE);
    assertThat(count("notice.notice_versions")).isEqualTo(1);
  }

  @Test
  void 옛_원본_버전이_내용이_같은_최신_버전보다_늦게_와도_덮어쓰지_않는다() {
    ingestion.apply(body(fixture()));
    ObjectNode sameContent = withRawVersion(fixture(), 3);
    sameContent.put("eventId", UUID.randomUUID().toString());
    assertThat(ingestion.apply(body(sameContent))).isEqualTo(IngestionOutcome.NO_CHANGE);

    ObjectNode late = withRawVersion(fixture(), 2);
    late.put("eventId", UUID.randomUUID().toString());
    ((ObjectNode) late.path("payload")).put("title", "늦게 온 옛 버전");
    ((ObjectNode) late.path("payload").path("notice").path("notice")).put("title", "늦게 온 옛 버전");

    assertThat(ingestion.apply(body(late))).isEqualTo(IngestionOutcome.STALE);
    assertThat(query.detail(onlyNotice()).header().title()).isNotEqualTo("늦게 온 옛 버전");
  }

  @Test
  void 같은_원본_버전의_승인본이_있으면_자동_결과로_바꾸지_않는다() {
    ingestion.apply(body(withStatus(fixture(), "APPROVED")));
    ObjectNode auto = fixture();
    auto.put("eventId", UUID.randomUUID().toString());
    ((ObjectNode) auto.path("payload")).put("title", "자동 결과");
    ((ObjectNode) auto.path("payload").path("notice").path("notice")).put("title", "자동 결과");

    assertThat(ingestion.apply(body(auto))).isEqualTo(IngestionOutcome.KEPT_APPROVED);
    assertThat(query.detail(onlyNotice()).reviewed()).isTrue();
  }

  @Test
  void 내용이_같은_승인본을_받으면_승인을_기록해_뒤의_자동_결과가_덮어쓰지_않는다() {
    // 자동 통과(보류·검수 조건 없음) 결과와 같은 내용을 검수자가 승인한 경우: 해시가 같아 그냥 두면 「변화 없음」으로 끝나요
    ObjectNode auto = load("/contracts/examples/extraction.completed.json");
    assertThat(ingestion.apply(body(auto))).isEqualTo(IngestionOutcome.PUBLISHED);
    assertThat(query.detail(onlyNotice()).reviewed()).isFalse();

    ObjectNode approved = withStatus(auto.deepCopy(), "APPROVED");
    approved.put("eventId", UUID.randomUUID().toString());
    assertThat(ingestion.apply(body(approved))).isEqualTo(IngestionOutcome.APPROVAL_RECORDED);
    assertThat(count("notice.notice_versions")).isEqualTo(1);
    assertThat(query.detail(onlyNotice()).reviewed()).isTrue();

    ObjectNode reprocessed = auto.deepCopy();
    reprocessed.put("eventId", UUID.randomUUID().toString());
    ((ObjectNode) reprocessed.path("payload")).put("title", "자동 결과");
    ((ObjectNode) reprocessed.path("payload").path("notice").path("notice")).put("title", "자동 결과");
    assertThat(ingestion.apply(body(reprocessed))).isEqualTo(IngestionOutcome.KEPT_APPROVED);
  }

  @Test
  void 공고가_아닌_분야는_기록만_남긴다() {
    ObjectNode policy = fixture();
    ((ObjectNode) policy.path("payload")).put("field", "POLICY");
    ((ObjectNode) policy.path("payload")).remove("notice");

    assertThat(ingestion.apply(body(policy))).isEqualTo(IngestionOutcome.UNSUPPORTED_FIELD);
    assertThat(count("notice.notices")).isZero();
    assertThat(outcomes()).containsExactly("UNSUPPORTED_FIELD:POLICY");
  }

  /** 정책 판정 틀만 실은 추출 결과 (창업지원·사업공간 모집, 2026-10-22). 상세(notice)·조건 없이 틀과 지원 지역만 있어요. */
  private ObjectNode policyEvent(String field, int version, String applyEnd, String... regions) {
    ObjectNode event = fixture();
    event.put("eventId", UUID.randomUUID().toString()); // 공고 fixture와 같은 eventId면 DUPLICATE
    ObjectNode payload = (ObjectNode) event.path("payload");
    payload.put("field", field);
    payload.put("rawVersion", version);
    payload.put("reviewStatus", "AUTO_PASSED");
    payload.remove("notice");
    payload.remove("heldItems");
    payload.putArray("conditions");
    payload.putArray("applicationWindows");
    payload.putNull("regionCode");
    ObjectNode schedule = payload.putObject("schedule");
    schedule.put("applyStartOn", "2026-10-07");
    schedule.put("applyEndOn", applyEnd);
    var codes = payload.putArray("regionCodes");
    for (String region : regions) codes.add(region);
    payload.put(
        "detailUrl", "https://www.k-startup.go.kr/web/contents/bizpbanc-ongoing.do?pbancSn=1");
    payload.put("applyAlways", false);
    boolean startup = field.equals("STARTUP_SUPPORT");
    ObjectNode frame = payload.putObject("judgment");
    frame.put("schema", startup ? "startup-support-judgment.v1" : "business-space-judgment.v1");
    frame.put(startup ? "rawPolicyId" : "rawPostId", payload.path("rawPostId").asString());
    frame.put("rawVersion", version);
    if (startup) frame.putNull("referenceDate");
    else frame.put("referenceDate", "2026-10-07");
    frame.putArray("common");
    frame.putArray("groups").addObject().put("id", "all").put("name", "전체").putArray("criteria");
    frame.putArray("preferences");
    frame.putArray("notes");
    return event;
  }

  @Test
  void 창업지원_판정_틀은_공고로_만들지_않고_판정용_창업지원_목록으로_준다() {
    // 판정 요청안(2026-10-22) 창업지원: findOpenProgramsForJudgment(). 사용자 결정으로 notice가 저장하고 줘요
    ObjectNode startup = policyEvent("STARTUP_SUPPORT", 2, "2026-11-02");

    assertThat(ingestion.apply(body(startup))).isEqualTo(IngestionOutcome.POLICY_JUDGMENT_SAVED);
    assertThat(count("notice.notices")).isZero();
    assertThat(outcomes()).containsExactly("POLICY_JUDGMENT_SAVED:STARTUP_SUPPORT");
    List<ProgramForJudgment> programs = query.findOpenProgramsForJudgment();
    assertThat(programs).hasSize(1);
    ProgramForJudgment program = programs.get(0);
    assertThat(program.programId().toString())
        .isEqualTo(startup.path("payload").path("rawPostId").asString());
    assertThat(program.version()).isEqualTo(2);
    assertThat(program.applyEnd()).isEqualTo(LocalDate.of(2026, 11, 2));
    assertThat(program.regionCodes()).isEmpty(); // 전국
    assertThat(program.frame().path("schema").asString()).isEqualTo("startup-support-judgment.v1");
    assertThat(query.findOpenForJudgment(NoticeField.BUSINESS_SPACE)).isEmpty();
  }

  @Test
  void 정책_출처_안내는_같이_저장하고_새_버전에_없으면_비운다() {
    ObjectNode startup = policyEvent("STARTUP_SUPPORT", 2, "2026-11-02");
    ((ObjectNode) startup.path("payload"))
        .putObject("policyInfo")
        .put("supportArea", "융자")
        .put("summary", "창업기업 운영자금을 빌려줍니다")
        .put("contact", "창업팀 02-000-0000")
        .putNull("organization")
        .putNull("applyMethod")
        .putNull("applyUrl")
        .putNull("guideUrl")
        .put("amountText", "최대 1억 원");
    UUID id = UUID.fromString(startup.path("payload").path("rawPostId").asString());

    assertThat(ingestion.apply(body(startup))).isEqualTo(IngestionOutcome.POLICY_JUDGMENT_SAVED);
    var info = query.policyInfos(List.of(id)).get(id);
    assertThat(info.supportArea()).isEqualTo("융자");
    assertThat(info.amountText()).isEqualTo("최대 1억 원");
    assertThat(info.organization()).isNull();

    // 다음 버전에 안내가 없으면(예전 형식 이벤트) 안내도 비워요
    ObjectNode newer = policyEvent("STARTUP_SUPPORT", 3, "2026-11-02");
    assertThat(ingestion.apply(body(newer))).isEqualTo(IngestionOutcome.POLICY_JUDGMENT_SAVED);
    assertThat(query.policyInfos(List.of(id))).isEmpty();
  }

  @Test
  void 사업공간_모집_판정_틀은_사업공간_판정_목록에_같이_준다() {
    ObjectNode space = policyEvent("SPACE_RECRUITMENT", 2, "2026-10-27", "11000");

    assertThat(ingestion.apply(body(space))).isEqualTo(IngestionOutcome.POLICY_JUDGMENT_SAVED);
    List<NoticeForJudgment> open = query.findOpenForJudgment(NoticeField.BUSINESS_SPACE);
    assertThat(open).hasSize(1);
    assertThat(open.get(0).regionCodes()).containsExactly("1100000000");
    assertThat(open.get(0).frame().path("schema").asString())
        .isEqualTo("business-space-judgment.v1");
    assertThat(query.findOpenProgramsForJudgment()).isEmpty();
    assertThat(query.findOpenForJudgment(NoticeField.HOUSING)).isEmpty();
  }

  @Test
  void 정책_판정_틀은_더_낮은_버전으로_덮지_않고_마감되면_목록에서_뺀다() {
    ObjectNode newer = policyEvent("STARTUP_SUPPORT", 3, "2026-10-20");
    ObjectNode older = newer.deepCopy();
    older.put("eventId", UUID.randomUUID().toString());
    ((ObjectNode) older.path("payload")).put("rawVersion", 2);
    ((ObjectNode) older.path("payload").path("judgment")).put("rawVersion", 2);

    assertThat(ingestion.apply(body(newer))).isEqualTo(IngestionOutcome.POLICY_JUDGMENT_SAVED);
    assertThat(ingestion.apply(body(older))).isEqualTo(IngestionOutcome.STALE);
    assertThat(query.findOpenProgramsForJudgment().get(0).version()).isEqualTo(3);

    clock.set("2026-10-21T00:05"); // 마감일 다음 날
    assertThat(query.findOpenProgramsForJudgment()).isEmpty();
  }

  @Test
  void 같은_버전의_승인된_정책_판정_틀은_승인_아닌_결과로_덮지_않는다() {
    // 리뷰 2026-10-22: 같은 rawVersion이면 IN_REVIEW·퇴화 틀이 승인본을 덮었음 (공고의 KEPT_APPROVED와 같은 규칙)
    ObjectNode approved = policyEvent("STARTUP_SUPPORT", 2, "2026-11-02");
    ((ObjectNode) approved.path("payload")).put("reviewStatus", "APPROVED");
    ((ObjectNode) approved.path("payload")).put("title", "승인본");
    ObjectNode later = policyEvent("STARTUP_SUPPORT", 2, "2026-11-02");
    later.put("eventId", UUID.randomUUID().toString());
    ((ObjectNode) later.path("payload"))
        .put("rawPostId", approved.path("payload").path("rawPostId").asString())
        .put("reviewStatus", "IN_REVIEW")
        .put("title", "자동 결과");
    ((ObjectNode) later.path("payload").path("judgment"))
        .put("rawPolicyId", approved.path("payload").path("rawPostId").asString());

    assertThat(ingestion.apply(body(approved))).isEqualTo(IngestionOutcome.POLICY_JUDGMENT_SAVED);
    assertThat(ingestion.apply(body(later))).isEqualTo(IngestionOutcome.KEPT_APPROVED);
    assertThat(query.findOpenProgramsForJudgment().get(0).title()).isEqualTo("승인본");
  }

  /** 같은 정책의 다른 결과 (새 eventId, 버전·검수 상태만 바꿈). */
  private static ObjectNode samePolicy(ObjectNode base, int version, String status) {
    ObjectNode event = base.deepCopy();
    event.put("eventId", UUID.randomUUID().toString());
    ((ObjectNode) event.path("payload")).put("rawVersion", version).put("reviewStatus", status);
    ((ObjectNode) event.path("payload").path("judgment")).put("rawVersion", version);
    return event;
  }

  /** 다른 정책으로 (새 정책 ID, 틀의 원본 ID도 같이). */
  private static ObjectNode otherPolicy(ObjectNode event) {
    String id = UUID.randomUUID().toString();
    ((ObjectNode) event.path("payload")).put("rawPostId", id);
    ObjectNode frame = (ObjectNode) event.path("payload").path("judgment");
    frame.put(frame.has("rawPolicyId") ? "rawPolicyId" : "rawPostId", id);
    return event;
  }

  /** 판정 틀 메모 하나 (AI가 쓴 글이라 다시 추출할 때마다 바뀔 수 있어요). */
  private ObjectNode note(String text) {
    return json.createObjectNode()
        .put("kind", "OTHER")
        .putNull("groupId")
        .put("text", text)
        .putNull("quote")
        .putNull("page");
  }

  /** 확인 필요(inReview) 조건 하나를 판정 틀 공통 조건에 넣어요. */
  private static ObjectNode withReviewCriterion(ObjectNode event) {
    ((ObjectNode) event.path("payload").path("judgment"))
        .putArray("common")
        .addObject()
        .put("kind", "BUSINESS_REGISTRATION")
        .put("id", "c1")
        .put("quote", "사업자등록을 한 자")
        .putNull("page")
        .put("inReview", true)
        .put("reviewReason", "확인 필요")
        .putNull("asOf")
        .put("require", "REGISTERED");
    return event;
  }

  @Test
  void 사업공간_판정_목록은_공고와_정책을_구분하고_원문_주소를_준다() {
    // 리뷰 2026-10-23 (PR #70): ID만으로는 정책을 공고 상세 API로 열어 NOTICE_NOT_FOUND가 났음
    ingestion.apply(body(fixture()));
    UUID noticeId = onlyNotice();
    jdbc.sql(
            "update notice.notices set field = 'BUSINESS_SPACE', status = 'APPLYING' where id = :id")
        .param("id", noticeId)
        .update();
    String noticeUrl =
        jdbc.sql("select detail_url from notice.notices where id = :id")
            .param("id", noticeId)
            .query(String.class)
            .single();
    ObjectNode space = policyEvent("SPACE_RECRUITMENT", 2, "2026-10-27", "11000");
    ingestion.apply(body(space));

    List<NoticeForJudgment> open = query.findOpenForJudgment(NoticeField.BUSINESS_SPACE);

    assertThat(open).hasSize(2);
    NoticeForJudgment notice = open.get(0);
    NoticeForJudgment policy = open.get(1);
    assertThat(notice.noticeId()).isEqualTo(noticeId);
    assertThat(notice.policy()).isFalse();
    assertThat(noticeUrl).isNotNull();
    assertThat(notice.detailUrl()).isEqualTo(noticeUrl);
    assertThat(policy.noticeId().toString())
        .isEqualTo(space.path("payload").path("rawPostId").asString());
    assertThat(policy.policy()).isTrue();
    assertThat(policy.detailUrl())
        .isEqualTo("https://www.k-startup.go.kr/web/contents/bizpbanc-ongoing.do?pbancSn=1");
  }

  @Test
  void 창업지원_판정_목록도_원문_주소를_주고_원문_주소를_모르면_null이다() {
    ObjectNode startup = policyEvent("STARTUP_SUPPORT", 2, "2026-11-02");
    ((ObjectNode) startup.path("payload")).putNull("detailUrl");

    ingestion.apply(body(startup));

    List<ProgramForJudgment> programs = query.findOpenProgramsForJudgment();
    assertThat(programs).hasSize(1);
    assertThat(programs.get(0).detailUrl()).isNull();
  }

  @Test
  void 마감일을_모르는데_상시_모집도_아닌_정책은_판정_목록에서_빼고_상시_모집은_넣는다() {
    // 리뷰 2026-10-23 (PR #70): 마감일이 없으면 열린 것으로 봐서 마감된 사업이 열려 보였음 (공고가 UNKNOWN을 빼는 것과 같게)
    ObjectNode unknown = otherPolicy(policyEvent("STARTUP_SUPPORT", 2, null));
    ObjectNode always = otherPolicy(policyEvent("STARTUP_SUPPORT", 2, null));
    ((ObjectNode) always.path("payload")).put("applyAlways", true).put("title", "상시 모집 사업");
    ObjectNode space = otherPolicy(policyEvent("SPACE_RECRUITMENT", 2, null, "11000"));

    assertThat(ingestion.apply(body(unknown))).isEqualTo(IngestionOutcome.POLICY_JUDGMENT_SAVED);
    assertThat(ingestion.apply(body(always))).isEqualTo(IngestionOutcome.POLICY_JUDGMENT_SAVED);
    assertThat(ingestion.apply(body(space))).isEqualTo(IngestionOutcome.POLICY_JUDGMENT_SAVED);

    assertThat(query.findOpenProgramsForJudgment())
        .extracting(ProgramForJudgment::title)
        .containsExactly("상시 모집 사업");
    assertThat(query.findOpenForJudgment(NoticeField.BUSINESS_SPACE)).isEmpty();
  }

  @Test
  void 같은_분야_이름_지역의_정책이_또_오면_중복_의심에_올리고_숨기면_목록에서_뺀다() {
    // 2026-10-28 사용자 결정 A안: 출처에 같은 사업이 두 번 올라오면(실측 온통청년) 지우지 않고 관리자 「중복 의심」에 올려요
    ObjectNode first = policyEvent("SPACE_RECRUITMENT", 2, "2026-12-31", "11000");
    ((ObjectNode) first.path("payload")).put("title", "청년창업 거주지원시설 입주자 1차 모집");
    ObjectNode again = otherPolicy(policyEvent("SPACE_RECRUITMENT", 2, "2026-12-31", "11000"));
    ((ObjectNode) again.path("payload")).put("title", "청년창업 거주지원시설(입주자) 1차  모집");
    ObjectNode elsewhere = otherPolicy(policyEvent("SPACE_RECRUITMENT", 2, "2026-12-31", "26000"));
    ((ObjectNode) elsewhere.path("payload")).put("title", "청년창업 거주지원시설 입주자 1차 모집");
    UUID firstId = UUID.fromString(first.path("payload").path("rawPostId").asString());
    UUID againId = UUID.fromString(again.path("payload").path("rawPostId").asString());

    ingestion.apply(body(first));
    ingestion.apply(body(again));
    ingestion.apply(body(elsewhere)); // 지역이 다르면 다른 사업

    var pending = duplicates.list("PENDING");
    assertThat(pending.items()).hasSize(1);
    assertThat(pending.items().get(0).later().id()).isEqualTo(againId);
    assertThat(pending.items().get(0).earlier().id()).isEqualTo(firstId);
    assertThat(pending.counts().pending()).isEqualTo(1);
    assertThat(query.findOpenForJudgment(NoticeField.BUSINESS_SPACE)).hasSize(3);

    duplicates.decide(againId, firstId, "HIDE_LATER", "admin-1");

    assertThat(query.findOpenForJudgment(NoticeField.BUSINESS_SPACE))
        .extracting(NoticeForJudgment::noticeId)
        .doesNotContain(againId)
        .contains(firstId);
    assertThat(duplicates.list("HIDDEN").items()).hasSize(1);
    assertThatThrownBy(() -> duplicates.decide(againId, firstId, "KEEP_BOTH", "admin-1"))
        .isInstanceOf(kr.mujuthaek.api.common.exception.CustomException.class);
  }

  @Test
  void 새_정책은_처음_저장할_때만_PolicyPublished를_보낸다() {
    ObjectNode space = policyEvent("SPACE_RECRUITMENT", 2, "2026-10-27", "11000");
    ((ObjectNode) space.path("payload")).put("title", "강남 창업공간 입주기업 모집");
    UUID id = UUID.fromString(space.path("payload").path("rawPostId").asString());

    assertThat(ingestion.apply(body(space))).isEqualTo(IngestionOutcome.POLICY_JUDGMENT_SAVED);
    assertThat(events.stream(PolicyPublished.class))
        .containsExactly(
            new PolicyPublished(
                id, "SPACE_RECRUITMENT", List.of("11000"), "강남 창업공간 입주기업 모집", false));

    // 같은 버전의 승인본·내용이 같은 새 버전은 새 소식도 정정도 아니에요
    ingestion.apply(body(samePolicy(space, 2, "APPROVED")));
    ingestion.apply(body(samePolicy(space, 3, "AUTO_PASSED")));
    assertThat(events.stream(PolicyPublished.class)).hasSize(1);
    assertThat(events.stream(PolicyUpdated.class)).isEmpty();
    assertThat(events.stream(NoticePublished.class)).isEmpty();
  }

  @Test
  void 검수_대기라_저장하지_않던_정책은_승인되어_처음_저장될_때_새_정책이다() {
    ObjectNode inReview =
        samePolicy(policyEvent("STARTUP_SUPPORT", 2, "2026-11-02"), 2, "IN_REVIEW");

    ingestion.apply(body(inReview));
    assertThat(events.stream(PolicyPublished.class)).isEmpty();

    ingestion.apply(body(samePolicy(inReview, 2, "APPROVED")));
    assertThat(events.stream(PolicyPublished.class)).hasSize(1);
  }

  @Test
  void 새_수집_버전에서_보이는_내용이_바뀌면_바뀐_부분과_함께_PolicyUpdated를_보낸다() {
    ObjectNode v2 = policyEvent("STARTUP_SUPPORT", 2, "2026-11-02");
    UUID id = UUID.fromString(v2.path("payload").path("rawPostId").asString());
    ingestion.apply(body(v2));

    // 마감일과 자격 조건이 바뀜 (판정 틀의 버전·메모도 바뀌지만 그것만으로는 정정이 아니에요)
    ObjectNode v3 = withReviewCriterion(samePolicy(v2, 3, "PARTIALLY_PASSED"));
    ((ObjectNode) v3.path("payload").path("schedule")).put("applyEndOn", "2026-11-09");
    ((ObjectNode) v3.path("payload").path("judgment")).putArray("notes").add(note("AI 메모"));
    ingestion.apply(body(v3));

    assertThat(events.stream(PolicyUpdated.class))
        .containsExactly(
            new PolicyUpdated(id, "STARTUP_SUPPORT", 3, List.of("schedule", "conditions"), false));

    ObjectNode v4 = samePolicy(v3, 4, "PARTIALLY_PASSED");
    ((ObjectNode) v4.path("payload").path("judgment")).putArray("notes").add(note("다른 AI 메모"));
    ((ObjectNode) v4.path("payload")).put("title", "바뀐 제목");
    ((ObjectNode) v4.path("payload"))
        .put("detailUrl", "https://www.k-startup.go.kr/web/contents/bizpbanc-ongoing.do?pbancSn=2");
    ingestion.apply(body(v4));

    assertThat(events.stream(PolicyUpdated.class))
        .last()
        .isEqualTo(
            new PolicyUpdated(id, "STARTUP_SUPPORT", 4, List.of("basic", "application"), false));
  }

  @Test
  void 조건의_근거_문장만_바뀐_새_버전은_자격_정정이_아니다() {
    ObjectNode v2 =
        withReviewCriterion(
            samePolicy(policyEvent("STARTUP_SUPPORT", 2, "2026-11-02"), 2, "PARTIALLY_PASSED"));
    ingestion.apply(body(v2));

    ObjectNode v3 = samePolicy(v2, 3, "PARTIALLY_PASSED");
    ObjectNode criterion = (ObjectNode) v3.path("payload").path("judgment").path("common").get(0);
    criterion.put("quote", "사업자 등록을 마친 사람").put("page", 2).put("reviewReason", "다시 확인");
    ingestion.apply(body(v3));

    assertThat(events.stream(PolicyUpdated.class)).isEmpty();

    ObjectNode v4 = samePolicy(v3, 4, "PARTIALLY_PASSED");
    ((ObjectNode) v4.path("payload").path("judgment").path("common").get(0))
        .put("require", "NOT_REGISTERED");
    ingestion.apply(body(v4));

    assertThat(events.stream(PolicyUpdated.class))
        .extracting(PolicyUpdated::changedFields)
        .containsExactly(List.of("conditions"));
  }

  @Test
  void 정책_요약과_마감_임박_정책을_조회한다() {
    ObjectNode startup = policyEvent("STARTUP_SUPPORT", 2, "2026-10-22");
    ((ObjectNode) startup.path("payload"))
        .putObject("policyInfo")
        .put("organization", "창업진흥원")
        .putNull("supportArea")
        .putNull("summary")
        .putNull("contact")
        .putNull("applyMethod")
        .putNull("applyUrl")
        .putNull("guideUrl")
        .putNull("amountText");
    UUID startupId = UUID.fromString(startup.path("payload").path("rawPostId").asString());
    ObjectNode later = otherPolicy(policyEvent("SPACE_RECRUITMENT", 2, "2026-10-25", "11000"));
    ObjectNode notStarted = otherPolicy(policyEvent("STARTUP_SUPPORT", 2, "2026-10-22"));
    ((ObjectNode) notStarted.path("payload").path("schedule")).put("applyStartOn", "2026-10-20");
    ingestion.apply(body(startup));
    ingestion.apply(body(later));
    ingestion.apply(body(notStarted));

    var summary = query.findPolicySummary(startupId).orElseThrow();
    assertThat(summary.field()).isEqualTo("STARTUP_SUPPORT");
    assertThat(summary.organization()).isEqualTo("창업진흥원");
    assertThat(summary.status()).isEqualTo("APPLYING");
    assertThat(summary.applyEnd()).isEqualTo(LocalDate.of(2026, 10, 22));
    assertThat(summary.regionCodes()).isEmpty();
    assertThat(query.findPolicySummary(UUID.randomUUID())).isEmpty();
    // 관심 목록은 여러 개를 한 번에 읽어요: 하나씩 읽은 것과 같고, 없는·공개 전 정책은 빠져요
    var many = query.findPolicySummaries(List.of(startupId, UUID.randomUUID()));
    assertThat(many).containsOnlyKeys(startupId);
    assertThat(many.get(startupId)).isEqualTo(summary);

    // 오늘 10/19: 10/22(D-3) 마감 중 이미 신청 중인 것만
    LocalDate today = LocalDate.of(2026, 10, 19);
    assertThat(
            query.findOpenPoliciesClosingOn(List.of(today.plusDays(3), today.plusDays(1)), today))
        .extracting(PolicySummary::policyId)
        .containsExactly(startupId);

    clock.set("2026-10-23T09:00");
    assertThat(query.findPolicySummary(startupId).orElseThrow().status()).isEqualTo("CLOSED");
  }

  @Test
  void 검수_대기_정책_틀은_첫_버전이면_공개하지_않고_승인되면_공개한다() {
    // 사용자 결정 2026-10-23: IN_REVIEW는 틀 전체를 믿을 수 없음 → 첫 버전은 승인(APPROVED) 전까지 공개하지 않음
    ObjectNode inReview =
        samePolicy(policyEvent("STARTUP_SUPPORT", 2, "2026-11-02"), 2, "IN_REVIEW");

    assertThat(ingestion.apply(body(inReview))).isEqualTo(IngestionOutcome.HELD);
    assertThat(outcomes()).containsExactly("HELD:POLICY_IN_REVIEW");
    assertThat(count("notice.policy_judgments")).isZero();
    assertThat(query.findOpenProgramsForJudgment()).isEmpty();

    ObjectNode approved = samePolicy(inReview, 2, "APPROVED");
    assertThat(ingestion.apply(body(approved))).isEqualTo(IngestionOutcome.POLICY_JUDGMENT_SAVED);
    List<ProgramForJudgment> programs = query.findOpenProgramsForJudgment();
    assertThat(programs).hasSize(1);
    assertThat(programs.get(0).version()).isEqualTo(2);
  }

  @Test
  void 공개된_정책_틀은_새_버전이_검수_대기면_이전_버전을_그대로_준다() {
    ObjectNode v2 = policyEvent("STARTUP_SUPPORT", 2, "2026-11-02");
    ((ObjectNode) v2.path("payload")).put("title", "2판");
    ObjectNode v3 = samePolicy(v2, 3, "IN_REVIEW");
    ((ObjectNode) v3.path("payload")).put("title", "3판 검수 대기");

    assertThat(ingestion.apply(body(v2))).isEqualTo(IngestionOutcome.POLICY_JUDGMENT_SAVED);
    assertThat(ingestion.apply(body(v3))).isEqualTo(IngestionOutcome.HELD);

    ProgramForJudgment served = query.findOpenProgramsForJudgment().get(0);
    assertThat(served.version()).isEqualTo(2);
    assertThat(served.title()).isEqualTo("2판");

    ObjectNode approved = samePolicy(v3, 3, "APPROVED");
    ((ObjectNode) approved.path("payload")).put("title", "3판 승인");
    assertThat(ingestion.apply(body(approved))).isEqualTo(IngestionOutcome.POLICY_JUDGMENT_SAVED);
    assertThat(query.findOpenProgramsForJudgment().get(0).title()).isEqualTo("3판 승인");
  }

  @Test
  void 일부_조건만_확인_필요한_정책_틀은_공개하고_그_조건은_틀에_표시된다() {
    ObjectNode partial =
        withReviewCriterion(
            samePolicy(policyEvent("STARTUP_SUPPORT", 2, "2026-11-02"), 2, "PARTIALLY_PASSED"));

    assertThat(ingestion.apply(body(partial))).isEqualTo(IngestionOutcome.POLICY_JUDGMENT_SAVED);

    ProgramForJudgment served = query.findOpenProgramsForJudgment().get(0);
    assertThat(served.frame().path("common").get(0).path("inReview").asBoolean()).isTrue();
  }

  @Test
  void 정책_이벤트의_새_칸과_검수_상태는_계약_검사기와_같게_본다() {
    // 확인 필요 조건이 있는 틀은 AUTO_PASSED일 수 없음
    ObjectNode auto = withReviewCriterion(policyEvent("STARTUP_SUPPORT", 2, "2026-11-02"));
    assertThatThrownBy(() -> ingestion.apply(body(auto)))
        .isInstanceOf(ExtractionEvent.InvalidEventException.class);
    // 정책 이벤트는 원문 주소·상시 여부가 반드시 있음
    for (String key : List.of("detailUrl", "applyAlways")) {
      ObjectNode missing = policyEvent("STARTUP_SUPPORT", 2, "2026-11-02");
      ((ObjectNode) missing.path("payload")).remove(key);
      assertThatThrownBy(() -> ingestion.apply(body(missing)))
          .as(key)
          .isInstanceOf(ExtractionEvent.InvalidEventException.class);
    }
    // 공고 분야에는 없음
    ObjectNode housing = fixture();
    ((ObjectNode) housing.path("payload")).put("applyAlways", false);
    assertThatThrownBy(() -> ingestion.apply(body(housing)))
        .isInstanceOf(ExtractionEvent.InvalidEventException.class);
    assertThat(count("notice.policy_judgments")).isZero();
    assertThat(count("notice.notices")).isZero();
  }

  @Test
  void 지역을_모르는_공고는_판정_목록에서_전국으로_주지_않는다() {
    // 리뷰 2026-10-22: 위치 지역이 보류·없음이라 지역 색인이 비면 빈 목록(전국)으로 나가 모든 지역이 충족됐음
    ingestion.apply(body(fixture()));
    jdbc.sql("delete from notice.notice_regions").update();

    List<NoticeForJudgment> open = query.findOpenForJudgment(NoticeField.HOUSING);

    assertThat(open).hasSize(1);
    assertThat(open.get(0).regionCodes()).isNull();
  }

  @Test
  void 판정_목록은_접수예정_접수중_상시만_준다() {
    ingestion.apply(body(fixture()));

    for (String status : List.of("UPCOMING", "APPLYING", "ALWAYS")) {
      jdbc.sql("update notice.notices set status = :s").param("s", status).update();
      assertThat(query.findOpenForJudgment(NoticeField.HOUSING)).as(status).hasSize(1);
    }
    for (String status : List.of("UNKNOWN", "CLOSED")) {
      jdbc.sql("update notice.notices set status = :s").param("s", status).update();
      assertThat(query.findOpenForJudgment(NoticeField.HOUSING)).as(status).isEmpty();
    }
  }

  @Test
  void 공고_분야에_정책용_지원_지역이_실려_오면_계약_위반이다() {
    // Python 계약 검사기와 같은 규칙(리뷰 2026-10-22): regionCodes는 정책(STARTUP_SUPPORT·SPACE_RECRUITMENT)만
    ObjectNode housing = fixture();
    ((ObjectNode) housing.path("payload")).putArray("regionCodes").add("11000");

    assertThatThrownBy(() -> ingestion.apply(body(housing)))
        .isInstanceOf(ExtractionEvent.InvalidEventException.class);
    assertThat(count("notice.notices")).isZero();
  }

  @Test
  void 정책_분야인데_판정_틀이나_지원_지역이_없으면_계약_위반이다() {
    ObjectNode missing = policyEvent("SPACE_RECRUITMENT", 2, "2026-10-27", "11000");
    ((ObjectNode) missing.path("payload")).remove("regionCodes");

    assertThatThrownBy(() -> ingestion.apply(body(missing)))
        .isInstanceOf(ExtractionEvent.InvalidEventException.class);
    assertThat(count("notice.policy_judgments")).isZero();
  }

  @Test
  void 계약에_맞지_않으면_아무것도_저장하지_않는다() {
    ObjectNode broken = fixture();
    ((ObjectNode) broken.path("payload")).put("reviewStatus", "DONE");

    assertThatThrownBy(() -> ingestion.apply(body(broken)))
        .isInstanceOf(ExtractionEvent.InvalidEventException.class);
    assertThatThrownBy(() -> ingestion.apply("not json"))
        .isInstanceOf(ExtractionEvent.InvalidEventException.class);
    assertThat(count("notice.extraction_results")).isZero();
  }

  @Test
  void 다른_형식_버전이나_상세와_보류_범위가_다른_이벤트는_받지_않는다() {
    ObjectNode future = fixture();
    future.put("schemaVersion", 999);
    ObjectNode conflict = fixture();
    ((ObjectNode) conflict.path("payload")).putArray("heldItems"); // 상세에는 보류 항목이 있음

    assertThatThrownBy(() -> ingestion.apply(body(future)))
        .isInstanceOf(ExtractionEvent.InvalidEventException.class)
        .hasMessageContaining("schemaVersion");
    assertThatThrownBy(() -> ingestion.apply(body(conflict)))
        .isInstanceOf(ExtractionEvent.InvalidEventException.class)
        .hasMessageContaining("heldItems");
    assertThat(count("notice.extraction_results")).isZero();
  }

  @Test
  void 원래_공고를_가리키지_않는_정정은_일반_공고로_공개하지_않고_보류한다() {
    ObjectNode correction = withStatus(correctionOf(fixture(), "2026-10-30"), "IN_REVIEW");
    ((ObjectNode) correction.path("payload").path("notice").path("sourceReferences").get(0))
        .putNull("supersedesPostId");

    assertThat(ingestion.apply(body(correction))).isEqualTo(IngestionOutcome.HELD);
    assertThat(count("notice.notices")).isZero();
    assertThat(outcomes()).containsExactly("HELD:UNLINKED_RELATED_NOTICE");
  }

  @Test
  void 저장_중_실패하면_처리_기록까지_되돌려져_다시_받으면_정상_처리된다() {
    ObjectNode event = fixture();
    doThrow(new IllegalStateException("저장 실패"))
        .when(results)
        .insert(any(), any(), anyInt(), any(), any(), any(), any(), any(), any(), any());

    assertThatThrownBy(() -> ingestion.apply(body(event))).hasMessageContaining("저장 실패");
    assertThat(count("notice.extraction_results")).isZero();
    assertThat(count("notice.notices")).isZero();

    org.mockito.Mockito.reset(results);
    assertThat(ingestion.apply(body(event))).isEqualTo(IngestionOutcome.PUBLISHED);
  }

  // ---------- 접수 상태 ----------

  @Test
  void 날짜가_지나면_접수_상태를_바꾸고_마감되면_NoticeClosed를_보낸다() {
    ingestion.apply(body(fixture()));
    UUID id = onlyNotice();
    assertThat(statusOf(id)).isEqualTo("UPCOMING");

    clock.set("2026-10-25T23:59");
    assertThat(status.refreshDue(10)).isZero(); // 다시 계산할 시각(10/26 0시) 전

    clock.set("2026-10-26T00:05");
    assertThat(status.refreshDue(10)).isEqualTo(1);
    assertThat(statusOf(id)).isEqualTo("APPLYING");
    assertThat(events.stream(NoticeClosed.class)).isEmpty();

    clock.set("2026-10-30T16:59");
    assertThat(status.refreshDue(10)).isZero(); // 원문 마감 시각(10/30 17:00) 전은 접수 중

    clock.set("2026-10-30T17:01"); // 날짜만 보면 그날 자정까지 접수 중으로 남아요
    assertThat(status.refreshDue(10)).isEqualTo(1);
    assertThat(statusOf(id)).isEqualTo("CLOSED");
    assertThat(events.stream(NoticeClosed.class))
        .containsExactly(new NoticeClosed(id, "HOUSING", LocalDate.of(2026, 10, 30)));

    clock.set("2026-12-31T00:00");
    assertThat(status.refreshDue(10)).isZero(); // 마감 뒤에는 다시 계산하지 않음
  }

  @Test
  void 재처리로_접수가_끝나도_마감_알림_이벤트는_보내지_않는다() {
    ingestion.apply(body(fixture()));
    UUID id = onlyNotice();
    clock.set("2026-10-31T00:05");
    ObjectNode reprocessed = correctionOf(fixture(), "2026-10-30");
    ((ObjectNode) reprocessed.path("payload")).put("reprocess", true);
    ((ObjectNode) reprocessed.path("payload").path("notice").path("input")).put("reprocess", true);
    events.clear();

    assertThat(ingestion.apply(body(reprocessed))).isEqualTo(IngestionOutcome.NEW_VERSION);
    assertThat(statusOf(id)).isEqualTo("CLOSED");
    assertThat(events.stream(NoticeClosed.class)).isEmpty();
  }

  @Test
  void 처음부터_마감인_공고는_NoticeClosed를_보내지_않는다() {
    clock.set("2026-11-15T10:00");
    ingestion.apply(body(fixture()));

    assertThat(statusOf(onlyNotice())).isEqualTo("CLOSED");
    assertThat(status.refreshDue(10)).isZero();
    assertThat(events.stream(NoticeClosed.class)).isEmpty();
  }

  @Test
  void 정정으로_접수가_끝나면_NoticeClosed를_보낸다() {
    clock.set("2026-10-27T10:00");
    ingestion.apply(body(fixture()));
    UUID id = onlyNotice();
    assertThat(statusOf(id)).isEqualTo("APPLYING");

    ObjectNode corrected = withRawVersion(fixture(), 2); // 마감일을 10/26로 앞당김
    corrected.put("eventId", UUID.randomUUID().toString());
    setApplicationEnd((ObjectNode) corrected.path("payload"), "2026-10-26");

    assertThat(ingestion.apply(body(corrected))).isEqualTo(IngestionOutcome.NEW_VERSION);
    assertThat(statusOf(id)).isEqualTo("CLOSED");
    assertThat(events.stream(NoticeClosed.class))
        .containsExactly(new NoticeClosed(id, "HOUSING", LocalDate.of(2026, 10, 26)));
  }

  @Test
  void 한_공고의_일정을_읽지_못해도_다른_공고의_상태_재계산은_계속한다() {
    ingestion.apply(body(fixture()));
    ingestion.apply(body(otherPost(fixture())));
    UUID broken =
        jdbc.sql("select id from notice.notices order by created_at, id limit 1")
            .query(UUID.class)
            .single();
    jdbc.sql(
            "update notice.notice_versions set payload = jsonb_set(payload, '{notice,schedules}',"
                + " (select jsonb_agg(jsonb_set(jsonb_set(s, '{startsAt}',"
                + " '{\"precision\": \"DAY\", \"value\": \"broken\"}'), '{endsAt}',"
                + " '{\"precision\": \"DAY\", \"value\": \"broken\"}'))"
                + " from jsonb_array_elements(payload->'notice'->'schedules') s))"
                + " where notice_id = :id")
        .param("id", broken)
        .update();

    clock.set("2026-10-31T00:05");
    assertThat(status.refreshDue(10)).isEqualTo(2);
    assertThat(
            jdbc.sql("select count(*) from notice.notices where status = 'CLOSED'")
                .query(Long.class)
                .single())
        .isEqualTo(1); // 읽을 수 있는 공고는 마감 처리
    assertThat(
            jdbc.sql("select next_status_check_at from notice.notices where id = :id")
                .param("id", broken)
                .query(java.time.OffsetDateTime.class)
                .single()
                .toInstant())
        .isAfter(clock.instant()); // 읽지 못한 공고는 하루 뒤로 미룸 (DB now()가 아니라 시험 시계 기준)
  }

  @Test
  void 날짜가_없으면_상시_모집이_아니라_확인_필요다() {
    assertThat(statusWithRollingSchedule(false, false)).isEqualTo("ALWAYS");
    clean();
    assertThat(statusWithRollingSchedule(false, true)).isEqualTo("UNKNOWN");
  }

  @Test
  void 보류한_일정의_상시_모집은_접수_상태에_쓰지_않는다() {
    assertThat(statusWithRollingSchedule(true, false)).isEqualTo("UNKNOWN");
  }

  @Test
  void 하위_필드가_보류된_일정은_주기_재계산에서도_상시_모집이_아니다() {
    statusWithRollingSchedule(true, false);
    UUID id = onlyNotice();
    jdbc.sql(
            "update notice.notices set next_status_check_at = '2026-10-18T00:00:00Z' where id = :id")
        .param("id", id)
        .update();
    assertThat(status.refreshDue(200)).isEqualTo(1);
    assertThat(statusOf(id)).isEqualTo("UNKNOWN");
  }

  /**
   * 접수 기간 없이 상시 모집 일정만 있는 공고를 반영하고 접수 상태를 돌려줘요. held면 상시 모집 칸을 보류하고, notRolling이면 상시 모집이라고 적히지 않은
   * 날짜 없는 일정이에요.
   */
  private String statusWithRollingSchedule(boolean held, boolean notRolling) {
    ObjectNode event = fixture();
    ObjectNode payload = (ObjectNode) event.path("payload");
    payload.remove("schedule");
    payload.remove("applicationWindows");
    JsonNode schedules = payload.path("notice").path("schedules");
    for (int i = 0; i < schedules.size(); i++) {
      ObjectNode schedule = (ObjectNode) schedules.get(i);
      if (schedule.path("kinds").toString().contains("APPLICATION")) {
        schedule.put("applicationMode", notRolling ? "UNKNOWN" : "ROLLING");
        schedule.putNull("startsAt").putNull("endsAt");
        schedule.put("endStatus", "CONDITIONAL").put("endCondition", "소진 시까지");
        if (held) {
          ObjectNode item =
              json.createObjectNode()
                  .put("target", "/schedules/" + i + "/applicationMode")
                  .put("extent", "ITEM")
                  .put("description", "원문 확인이 필요합니다.");
          item.putArray("codes").add("CHECK");
          ((ArrayNode) payload.path("heldItems")).add(item);
          ((ArrayNode) payload.path("notice").path("quality").path("heldItems"))
              .add(item.deepCopy());
        }
      }
    }
    ingestion.apply(body(event));
    return statusOf(onlyNotice());
  }

  // ---------- 보류 항목 ----------

  @Test
  void 보류한_항목은_상세에서_빼고_확인_필요로_알린다() {
    ingestion.apply(body(fixture())); // 서리풀 공고는 자격 조건 하나를 보류했어요
    UUID id = onlyNotice();

    NoticeDetailResponse detail = query.detail(id);
    assertThat(detail.header().needsCheck()).isTrue();
    assertThat(detail.heldItems())
        .isNotEmpty()
        .allSatisfy(h -> assertThat(h.description()).isNotBlank());
    String heldTarget = detail.heldItems().getFirst().target();
    assertThat(heldTarget).startsWith("/eligibility/");
    int index = Integer.parseInt(heldTarget.split("/")[2]);
    assertThat(detail.conditions().get(index).inReview()).isTrue();

    ingestion.apply(body(otherPost(withStatus(fixture(), "APPROVED"))));
    assertThat(
            jdbc.sql("select needs_check from notice.notices order by created_at, id")
                .query(Boolean.class)
                .list())
        .containsExactly(true, false); // 승인본은 보류 항목이 없어요
  }

  // ---------- 지역 ----------

  @Test
  void 여러_시도에_걸친_공고는_공개_이벤트에_모든_지역을_담는다() {
    // 「대구경북지역 … 모집공고」: 대표 지역 하나(regionCode)는 null이지만 알림이 고를 지역 목록은 대구·경북 모두
    ObjectNode envelope = load("/contracts/examples/extraction.completed.json");
    ArrayNode locations = (ArrayNode) envelope.path("payload").path("notice").path("locations");
    ObjectNode first = (ObjectNode) locations.get(0);
    first.put("kind", "AREA").put("region", "대구").put("regionCode", "2700000000");
    ObjectNode second = first.deepCopy();
    second.put("id", "area-gyeongbuk").put("region", "경북").put("regionCode", "4700000000");
    locations.add(second);
    ((ObjectNode) envelope.path("payload")).putNull("regionCode");

    assertThat(ingestion.apply(body(envelope))).isEqualTo(IngestionOutcome.PUBLISHED);
    assertThat(events.stream(NoticePublished.class))
        .singleElement()
        .satisfies(
            e -> {
              assertThat(e.regionCode()).isNull();
              assertThat(e.regionCodes()).containsExactly("27000", "47000");
              assertThat(e.nationwide()).isFalse();
            });
  }

  @Test
  void 시도_단위로_검색하면_시도_단위_공고와_그_시도의_모든_구_공고가_나온다() {
    // 지역은 앞 5자리만 쓰고, 11000(서울특별시)으로 검색하면 11로 시작하는 공고가 모두 나와요
    ingestion.apply(body(fixture())); // 서초구(11650) 공고
    ObjectNode seoulWide = otherPost(fixture()); // 서울까지만 아는 위치의 공고
    for (JsonNode location : seoulWide.path("payload").path("notice").path("locations")) {
      ((ObjectNode) location).put("regionCode", "1100000000");
    }
    ((ObjectNode) seoulWide.path("payload")).put("regionCode", "11000");
    ingestion.apply(body(seoulWide));

    assertThat(listIn("11000")).hasSize(2);
    assertThat(listIn("11")).hasSize(2);
    assertThat(listIn("11650")).hasSize(1); // 구 검색에는 시도 단위 공고가 나오지 않음
    assertThat(listIn("11680")).isEmpty(); // 강남구
    assertThat(listIn("26000")).isEmpty();
  }

  @Test
  void 전국_대상_공고는_어느_지역으로_검색해도_나온다() {
    ingestion.apply(body(fixture())); // 서초구(11650) 공고
    ObjectNode nationwide = otherPost(fixture()); // 「사업대상지역 : 전국」 공고: 위치는 「전국」, 지역 코드 없음
    JsonNode detail = nationwide.path("payload").path("notice");
    ArrayNode missing = (ArrayNode) detail.path("quality").path("missingFields");
    for (int i = 0; i < detail.path("locations").size(); i++) {
      ((ObjectNode) detail.path("locations").get(i)).put("region", "전국").putNull("regionCode");
      missing
          .addObject()
          .put("target", "/locations/" + i + "/regionCode")
          .put("reason", "NOT_APPLICABLE")
          .put("description", "전국 대상이라 지역 코드가 없습니다.");
    }
    ((ObjectNode) nationwide.path("payload")).putNull("regionCode");
    ingestion.apply(body(nationwide));

    assertThat(listIn("11000")).hasSize(2);
    assertThat(listIn("11680")).hasSize(1);
    assertThat(listIn("26")).hasSize(1);
    assertThat(
            jdbc.sql("select count(*) from notice.notices where nationwide")
                .query(Long.class)
                .single())
        .isEqualTo(1);
  }

  @Test
  void 대상_지역_전체_공고는_그_시도의_구_검색에도_나온다() {
    // 「대구경북지역 … 모집공고」처럼 단지가 없는 공고: 대상 지역을 대구·경북 AREA로 적음
    ingestion.apply(body(fixture())); // 서초구(11650) 공고
    ObjectNode regional = otherPost(fixture());
    ArrayNode locations = (ArrayNode) regional.path("payload").path("notice").path("locations");
    ((ObjectNode) locations.get(0))
        .put("kind", "AREA")
        .put("region", "대구")
        .put("regionCode", "2700000000");
    ((ObjectNode) locations.get(1))
        .put("kind", "AREA")
        .put("region", "경북")
        .put("regionCode", "4700000000");
    ((ObjectNode) regional.path("payload")).putNull("regionCode");
    ingestion.apply(body(regional));

    assertThat(listIn("27000")).hasSize(1);
    assertThat(listIn("27110")).hasSize(1); // 대구 중구 검색에도 대구 전체 대상 공고
    assertThat(listIn("47")).hasSize(1);
    assertThat(listIn("11")).hasSize(1); // 서울 검색에는 서초구 공고만
    assertThat(listIn("26000")).isEmpty();
  }

  // ---------- 정정 공고 ----------

  @Test
  void 정정_공고는_원래_공고의_새_버전으로_반영한다() {
    ingestion.apply(body(fixture()));
    UUID id = onlyNotice();

    assertThat(ingestion.apply(body(correctionOf(fixture(), "2026-11-06"))))
        .isEqualTo(IngestionOutcome.NEW_VERSION);

    NoticeDetailResponse detail = query.detail(id);
    assertThat(detail.version()).isEqualTo(2);
    assertThat(detail.header().applyEnd()).isEqualTo(LocalDate.of(2026, 11, 6));
    assertThat(count("notice.notice_posts")).isEqualTo(2);
    assertThat(query.versions(id))
        .extracting(v -> v.kind())
        .containsExactly("NOTICE", "CORRECTION");
    assertThat(events.stream(NoticeUpdated.class))
        .singleElement()
        .satisfies(e -> assertThat(e.noticeId()).isEqualTo(id));
  }

  @Test
  void 원래_공고보다_먼저_온_정정은_기다렸다가_원래_공고가_공개될_때_반영한다() {
    ObjectNode correction = correctionOf(fixture(), "2026-11-06");
    assertThat(ingestion.apply(body(correction))).isEqualTo(IngestionOutcome.HELD);
    assertThat(count("notice.notices")).isZero();
    assertThat(outcomes()).containsExactly("HELD:PARENT_NOT_PUBLISHED");

    assertThat(ingestion.apply(body(fixture()))).isEqualTo(IngestionOutcome.PUBLISHED);

    NoticeDetailResponse detail = query.detail(onlyNotice());
    assertThat(detail.version()).isEqualTo(2);
    assertThat(detail.header().applyEnd()).isEqualTo(LocalDate.of(2026, 11, 6));
    assertThat(outcomes()).containsExactlyInAnyOrder("NEW_VERSION", "PUBLISHED");
    assertThat(events.stream(NoticePublished.class)).hasSize(1);
    assertThat(events.stream(NoticeUpdated.class)).hasSize(1);
  }

  @Test
  void 기다리던_정정의_저장본이_계약에_맞지_않아도_원래_공고는_공개한다() {
    ObjectNode correction = correctionOf(fixture(), "2026-11-06");
    assertThat(ingestion.apply(body(correction))).isEqualTo(IngestionOutcome.HELD);
    // 계약 검사가 강화된 뒤라고 가정: 저장해 둔 정정이 지금 검사에 걸림
    jdbc.sql(
            "update notice.extraction_results set payload = jsonb_set(payload, '{reviewStatus}',"
                + " '\"DONE\"') where event_id = :id")
        .param("id", UUID.fromString(correction.path("eventId").asString()))
        .update();

    assertThat(ingestion.apply(body(fixture()))).isEqualTo(IngestionOutcome.PUBLISHED);
    assertThat(count("notice.notices")).isEqualTo(1);
    assertThat(outcomes()).contains("HELD:STORED_PAYLOAD_INVALID");
  }

  @Test
  void 정정이_반영된_뒤_원래_공고가_바뀌어도_정정_내용을_덮어쓰지_않는다() {
    ingestion.apply(body(fixture()));
    ingestion.apply(body(correctionOf(fixture(), "2026-11-06")));
    ObjectNode originalEdited = withRawVersion(fixture(), 2);
    originalEdited.put("eventId", UUID.randomUUID().toString());
    ((ObjectNode) originalEdited.path("payload")).put("title", "원래 공고 수정");
    ((ObjectNode) originalEdited.path("payload").path("notice").path("notice"))
        .put("title", "원래 공고 수정");

    assertThat(ingestion.apply(body(originalEdited))).isEqualTo(IngestionOutcome.KEPT_CORRECTION);
    assertThat(count("notice.notice_versions")).isEqualTo(2);
    assertThat(query.detail(onlyNotice()).header().applyEnd()).isEqualTo(LocalDate.of(2026, 11, 6));
  }

  @Test
  void 늦게_도착한_더_이른_정정은_최신_정정을_덮어쓰지_않는다() {
    ingestion.apply(body(fixture()));
    ObjectNode later = postedOn(correctionOf(fixture(), "2026-11-10"), "2026-10-15");
    ObjectNode earlier = postedOn(correctionOf(fixture(), "2026-11-06"), "2026-10-10");

    assertThat(ingestion.apply(body(later))).isEqualTo(IngestionOutcome.NEW_VERSION);
    assertThat(ingestion.apply(body(earlier))).isEqualTo(IngestionOutcome.KEPT_CORRECTION);

    assertThat(count("notice.notice_versions")).isEqualTo(2);
    assertThat(query.detail(onlyNotice()).header().applyEnd())
        .isEqualTo(LocalDate.of(2026, 11, 10));
    assertThat(outcomes()).contains("KEPT_CORRECTION:LATER_CORRECTION_APPLIED");
  }

  @Test
  void 검수_대기인_정정은_기존_공개_버전을_유지한다() {
    ingestion.apply(body(fixture()));

    assertThat(
            ingestion.apply(body(withStatus(correctionOf(fixture(), "2026-11-06"), "IN_REVIEW"))))
        .isEqualTo(IngestionOutcome.HELD);
    assertThat(count("notice.notice_versions")).isEqualTo(1);
  }

  // ---------- 후속 안내 ----------

  @Test
  void 후속_안내는_원래_공고의_버전을_바꾸지_않고_상세에_붙인다() {
    ingestion.apply(body(fixture()));
    UUID id = onlyNotice();

    assertThat(ingestion.apply(body(followUpOf(fixture(), "서류 제출 안내"))))
        .isEqualTo(IngestionOutcome.FOLLOW_UP_ATTACHED);

    assertThat(count("notice.notices")).isEqualTo(1);
    NoticeDetailResponse detail = query.detail(id);
    assertThat(detail.version()).isEqualTo(1);
    assertThat(detail.followUps())
        .singleElement()
        .satisfies(
            f -> {
              assertThat(f.title()).isEqualTo("서류 제출 안내");
              assertThat(f.detailUrl()).startsWith("https://");
              assertThat(f.schedules()).isNotEmpty();
            });
    assertThat(events.stream(NoticeUpdated.class))
        .singleElement()
        .satisfies(
            e -> {
              assertThat(e.field()).isEqualTo("HOUSING");
              assertThat(e.changedFields()).containsExactly("followUps");
            });
  }

  @Test
  void 원래_공고보다_먼저_온_후속_안내는_기다렸다가_붙인다() {
    assertThat(ingestion.apply(body(followUpOf(fixture(), "당첨자 발표"))))
        .isEqualTo(IngestionOutcome.HELD);
    assertThat(outcomes()).containsExactly("HELD:PARENT_NOT_PUBLISHED");

    ingestion.apply(body(fixture()));

    assertThat(query.detail(onlyNotice()).followUps()).hasSize(1);
    assertThat(outcomes()).containsExactlyInAnyOrder("PUBLISHED", "FOLLOW_UP_ATTACHED");
  }

  @Test
  void 같은_후속_안내의_새_버전은_내용을_바꾸고_같은_내용이면_그대로_둔다() {
    ingestion.apply(body(fixture()));
    ObjectNode first = followUpOf(fixture(), "서류 제출 안내");
    ingestion.apply(body(first));

    ObjectNode same = first.deepCopy();
    same.put("eventId", UUID.randomUUID().toString());
    assertThat(ingestion.apply(body(same))).isEqualTo(IngestionOutcome.NO_CHANGE);

    ObjectNode edited = withRawVersion(first.deepCopy(), 2);
    edited.put("eventId", UUID.randomUUID().toString());
    ((ObjectNode) edited.path("payload").path("notice").path("sourceReferences").get(0))
        .put("sourceTitle", "서류 제출 안내 (일정 변경)");
    assertThat(ingestion.apply(body(edited))).isEqualTo(IngestionOutcome.FOLLOW_UP_ATTACHED);

    assertThat(count("notice.notice_follow_ups")).isEqualTo(1);
    assertThat(query.detail(onlyNotice()).followUps())
        .singleElement()
        .satisfies(f -> assertThat(f.title()).isEqualTo("서류 제출 안내 (일정 변경)"));
  }

  @Test
  void 승인한_후속_안내는_같은_원본_버전의_자동_결과로_덮어쓰지_않는다() {
    ingestion.apply(body(fixture()));
    ObjectNode automatic = followUpOf(fixture(), "서류 제출 안내");
    ObjectNode approved = withStatus(automatic.deepCopy(), "APPROVED");
    assertThat(ingestion.apply(body(approved))).isEqualTo(IngestionOutcome.FOLLOW_UP_ATTACHED);

    automatic.put("eventId", UUID.randomUUID().toString());
    ((ObjectNode) automatic.path("payload").path("notice").path("sourceReferences").get(0))
        .put("sourceTitle", "자동 결과 제목");

    assertThat(ingestion.apply(body(automatic))).isEqualTo(IngestionOutcome.KEPT_APPROVED);
    assertThat(query.detail(onlyNotice()).followUps())
        .singleElement()
        .satisfies(f -> assertThat(f.title()).isEqualTo("서류 제출 안내"));
  }

  @Test
  void 검수_대기인_후속_안내는_붙이지_않는다() {
    ingestion.apply(body(fixture()));

    assertThat(ingestion.apply(body(withStatus(followUpOf(fixture(), "발표"), "IN_REVIEW"))))
        .isEqualTo(IngestionOutcome.HELD);
    assertThat(count("notice.notice_follow_ups")).isZero();
  }

  // ---------- 같은 공고 합치기 ----------

  @Test
  void 다른_출처의_같은_공고는_자동으로_합치고_회차가_다른_공고는_따로_둔다() {
    ingestion.apply(body(fixture()));
    UUID kept = onlyNotice();
    events.clear();

    assertThat(ingestion.apply(body(samePostElsewhere(fixture()))))
        .isEqualTo(IngestionOutcome.PUBLISHED);
    assertThat(outcomes()).contains("PUBLISHED:AUTO_MERGED");
    assertThat(onlyNotice()).isEqualTo(kept); // 목록에 한 번만
    assertThat(events.stream(NoticePublished.class)).isEmpty(); // 새 공고 알림은 보내지 않음
    assertThat(events.stream(NoticeUpdated.class))
        .singleElement()
        .satisfies(
            e -> {
              assertThat(e.field()).isEqualTo("HOUSING");
              assertThat(e.changedFields()).containsExactly("sources");
            });
    assertThat(merges.pendingCandidates()).isEmpty(); // 합친 후보는 정리됨

    ingestion.apply(body(otherPost(fixture()))); // 모집 회차가 다른 공고
    assertThat(listed()).hasSize(2);
  }

  @Test
  void 정정을_다시_정정한_글도_원래_공고에_반영된다() {
    // 원공고 N → 정정 C1 → C1을 정정하는 C2: 줄기의 출처는 N이라 C2도 기준 출처의 새 버전이에요
    ingestion.apply(body(fixture()));
    UUID id = onlyNotice();
    ObjectNode first = correctionOf(fixture(), "2026-10-31");
    assertThat(ingestion.apply(body(first))).isEqualTo(IngestionOutcome.NEW_VERSION);

    ObjectNode second = correctionOf(first.deepCopy(), "2026-11-02"); // C1을 가리킴
    assertThat(ingestion.apply(body(second))).isEqualTo(IngestionOutcome.NEW_VERSION);
    assertThat(query.detail(id).header().applyEnd()).isEqualTo(LocalDate.of(2026, 11, 2));
  }

  @Test
  void 새_버전을_만들지_않은_정정도_공고에_이어_그_정정을_다시_정정한_글이_반영된다() {
    // 원공고 N → 보이는 변화 없는 정정 C1(NO_CHANGE) → C1을 정정하는 C2: C1이 공고에 이어져 있어야 C2가 원래 공고를 찾아요
    ingestion.apply(body(fixture()));
    UUID id = onlyNotice();
    ObjectNode first = unchangedCorrection();
    assertThat(ingestion.apply(body(first))).isEqualTo(IngestionOutcome.NO_CHANGE);
    assertThat(count("notice.notice_posts")).isEqualTo(2);

    ObjectNode second = correctionOf(first.deepCopy(), "2026-11-02");
    assertThat(ingestion.apply(body(second))).isEqualTo(IngestionOutcome.NEW_VERSION);
    assertThat(query.detail(id).header().applyEnd()).isEqualTo(LocalDate.of(2026, 11, 2));
  }

  @Test
  void 정정의_정정이_먼저_와_기다리면_새_버전_없이_이어진_정정에서_풀린다() {
    ingestion.apply(body(fixture()));
    UUID id = onlyNotice();
    ObjectNode first = unchangedCorrection();
    ObjectNode second = correctionOf(first.deepCopy(), "2026-11-02");
    assertThat(ingestion.apply(body(second))).isEqualTo(IngestionOutcome.HELD);

    assertThat(ingestion.apply(body(first))).isEqualTo(IngestionOutcome.NO_CHANGE);

    assertThat(query.detail(id).header().applyEnd()).isEqualTo(LocalDate.of(2026, 11, 2));
    assertThat(outcomes()).doesNotContain("HELD:PARENT_NOT_PUBLISHED").contains("NEW_VERSION");
  }

  @Test
  void 검수_대기인_정정은_공고에_잇지_않아_그_정정을_다시_정정한_글은_기다린다() {
    ingestion.apply(body(fixture()));
    ObjectNode first = withStatus(correctionOf(fixture(), "2026-11-06"), "IN_REVIEW");
    assertThat(ingestion.apply(body(first))).isEqualTo(IngestionOutcome.HELD);
    assertThat(count("notice.notice_posts")).isEqualTo(1);

    ObjectNode second =
        withStatus(correctionOf(first.deepCopy(), "2026-11-02"), "PARTIALLY_PASSED");
    assertThat(ingestion.apply(body(second))).isEqualTo(IngestionOutcome.HELD);
    assertThat(outcomes()).last().isEqualTo("HELD:PARENT_NOT_PUBLISHED");
  }

  @Test
  void 분야가_다른_같은_공고_후보가_있어도_새_공고는_정상으로_공개된다() {
    // 합칠 수 없는 후보(분야 다름)를 합치려다 예외가 나면 트랜잭션이 롤백 표시돼 정상 공고 저장까지 되돌아가요
    ingestion.apply(body(fixture()));
    UUID other = onlyNotice();
    jdbc.sql("update notice.notices set field = 'BUSINESS_SPACE' where id = :id")
        .param("id", other)
        .update();

    assertThat(ingestion.apply(body(samePostElsewhere(fixture()))))
        .isEqualTo(IngestionOutcome.PUBLISHED);
    assertThat(listed()).hasSize(2);
    assertThat(outcomes()).doesNotContain("PUBLISHED:AUTO_MERGED");
  }

  @Test
  void 다른_출처의_같은_공고가_동시에_들어와도_하나만_공개된다() throws Exception {
    // 원본 글 단위 잠금만으로는 출처가 다른 같은 공고가 동시에 오면 둘 다 공개돼요
    java.util.concurrent.CyclicBarrier start = new java.util.concurrent.CyclicBarrier(2);
    java.util.concurrent.ExecutorService pool =
        java.util.concurrent.Executors.newFixedThreadPool(2);
    try {
      List<java.util.concurrent.Future<IngestionOutcome>> done = new java.util.ArrayList<>();
      for (int i = 0; i < 2; i++) {
        String body = body(samePostElsewhere(fixture()));
        done.add(
            pool.submit(
                () -> {
                  start.await();
                  return ingestion.apply(body);
                }));
      }
      for (var f : done) {
        assertThat(f.get(60, java.util.concurrent.TimeUnit.SECONDS))
            .isEqualTo(IngestionOutcome.PUBLISHED);
      }
    } finally {
      pool.shutdownNow();
    }
    assertThat(listed()).hasSize(1);
    assertThat(outcomes()).contains("PUBLISHED:AUTO_MERGED");
  }

  @Test
  void 공고일이_한_달_넘게_차이나면_같은_공고로_보지_않는다() {
    ingestion.apply(body(fixture()));
    ingestion.apply(body(announcedLater(samePostElsewhere(fixture()))));
    assertThat(listed()).hasSize(2);
  }

  @Test
  void 다시_훑기는_이미_따로_공개된_같은_공고를_먼저_공고에_합친다() {
    ingestion.apply(body(fixture()));
    UUID kept = onlyNotice();
    LocalDate announced =
        jdbc.sql("select announced_on from notice.notices where id = :id")
            .param("id", kept)
            .query(LocalDate.class)
            .single();
    clock.set("2026-10-19T10:00"); // 먼저 공개된 공고에 합쳐요
    ingestion.apply(body(announcedLater(samePostElsewhere(fixture())))); // 공개 당시 규칙으로는 다른 공고
    ingestion.apply(body(otherPost(fixture()))); // 모집 회차가 다른 공고
    UUID separate =
        jdbc.sql("select id from notice.notices where id <> :kept and announced_on <> :on")
            .param("kept", kept)
            .param("on", announced)
            .query(UUID.class)
            .single();
    // 규칙이 바뀌어 이제는 같은 공고로 판정되는 상황: 공고일을 맞춰요
    jdbc.sql("update notice.notices set announced_on = :on where id = :id")
        .param("on", announced)
        .param("id", separate)
        .update();
    assertThat(listed()).hasSize(3);
    events.clear();

    assertThat(ingestion.mergeDuplicates()).isEqualTo(1);

    assertThat(listed()).hasSize(2); // 회차가 다른 공고는 그대로
    assertThat(query.detail(separate).header().id()).isEqualTo(kept);
    assertThat(merges.pendingCandidates()).isEmpty();
    assertThat(events.stream(NoticeUpdated.class))
        .anySatisfy(
            e -> {
              assertThat(e.noticeId()).isEqualTo(kept);
              assertThat(e.changedFields()).contains("sources");
            });
    assertThat(ingestion.mergeDuplicates()).isZero(); // 다시 돌려도 더 합칠 공고 없음
  }

  @Test
  void 되돌리거나_같은_공고가_아니라고_한_공고는_다시_훑어도_합치지_않는다() {
    ingestion.apply(body(fixture()));
    UUID kept = onlyNotice();
    clock.set("2026-10-19T10:00");
    ingestion.apply(body(samePostElsewhere(fixture())));
    UUID merged = mergedInto(kept);

    ingestion.unmerge(merged);
    assertThat(ingestion.mergeDuplicates()).isZero(); // 되돌린 쌍은 다시 합치지 않음
    assertThat(listed()).hasSize(2);

    ingestion.apply(body(otherPost(fixture())));
    UUID third =
        jdbc.sql("select id from notice.notices where id not in (:a, :b)")
            .param("a", kept)
            .param("b", merged)
            .query(UUID.class)
            .single();
    jdbc.sql(
            "update notice.notices set title = (select title from notice.notices where id = :kept)"
                + " where id = :id")
        .param("kept", kept)
        .param("id", third)
        .update(); // 규칙상 같은 공고가 되게
    merges.reject(third, kept);
    merges.reject(third, merged);
    assertThat(ingestion.mergeDuplicates()).isZero(); // 같은 공고가 아니라고 표시한 쌍도
  }

  @Test
  void 합치면_한_공고만_남고_합쳐진_공고의_원본_글은_남은_공고의_새_버전이_된다() {
    ingestion.apply(body(fixture()));
    UUID kept = onlyNotice();
    ObjectNode duplicate = samePostElsewhere(fixture());
    ingestion.apply(body(duplicate)); // 같은 공고라 자동으로 합쳐짐
    UUID merged = mergedInto(kept);

    assertThat(onlyNotice()).isEqualTo(kept);
    assertThat(query.detail(merged).header().id()).isEqualTo(kept); // 합쳐진 공고 ID로도 열려요
    assertThat(query.versions(merged)).hasSize(1); // 남은 공고의 이력
    assertThat(merges.pendingCandidates()).isEmpty();
    assertThat(events.stream(NoticeUpdated.class))
        .anySatisfy(e -> assertThat(e.changedFields()).containsExactly("sources"));

    // 기준 출처는 먼저 들어온 원래 공고(둘 다 같은 게시일): 다른 출처의 새 버전은 출처 기록만 바꾸고 공고 내용은 그대로예요
    ObjectNode next = withRawVersion(duplicate.deepCopy(), 2);
    next.put("eventId", UUID.randomUUID().toString());
    ((ObjectNode) next.path("payload")).put("title", "다른 출처에서 고친 제목");
    ((ObjectNode) next.path("payload").path("notice").path("notice")).put("title", "다른 출처에서 고친 제목");
    assertThat(ingestion.apply(body(next))).isEqualTo(IngestionOutcome.KEPT_BASE_SOURCE);
    assertThat(query.detail(kept).header().title()).isNotEqualTo("다른 출처에서 고친 제목");

    // 2026-11-10 코드 검토: 기준이 아닌 출처의 정정은 잇기만 하고 반영하지 않으니, 기준 출처의 새 버전을 「정정 반영됨」으로 막으면 안 돼요
    // (예전엔 그 정정을 세어 기준 출처의 수정이 KEPT_CORRECTION으로 막혀 공고가 옛 값으로 굳었음)
    assertThat(ingestion.apply(body(correctionOf(duplicate.deepCopy(), "2026-11-06"))))
        .isEqualTo(IngestionOutcome.KEPT_BASE_SOURCE);
    ObjectNode baseNext = withRawVersion(fixture(), 2);
    baseNext.put("eventId", UUID.randomUUID().toString());
    ((ObjectNode) baseNext.path("payload")).put("title", "기준 출처에서 고친 제목");
    ((ObjectNode) baseNext.path("payload").path("notice").path("notice"))
        .put("title", "기준 출처에서 고친 제목");
    assertThat(ingestion.apply(body(baseNext))).isEqualTo(IngestionOutcome.NEW_VERSION);
    assertThat(query.detail(kept).header().title()).isEqualTo("기준 출처에서 고친 제목");
  }

  @Test
  void 먼저_게시된_출처가_합쳐지면_기준_출처가_되어_공고_내용이_그_출처로_바뀌고_버전을_이어_간다() {
    ingestion.apply(body(fixture())); // 게시일 10-16
    UUID kept = onlyNotice();
    String title = "서리풀 청년아트타운 잔여세대 모집 (먼저 게시된 출처)";
    ObjectNode earlier = postedOn(samePostElsewhere(fixture()), "2026-10-10");
    ((ObjectNode) earlier.path("payload")).put("title", title);
    ((ObjectNode) earlier.path("payload").path("notice").path("notice")).put("title", title);

    assertThat(ingestion.apply(body(earlier))).isEqualTo(IngestionOutcome.PUBLISHED);
    assertThat(onlyNotice()).isEqualTo(kept); // 공고 ID는 그대로
    NoticeDetailResponse detail = query.detail(kept);
    assertThat(detail.header().title()).isEqualTo(title);
    assertThat(detail.version()).isEqualTo(2); // 남은 공고의 버전을 이어 가요

    // 이제 원래 공고 글은 기준이 아니라 새 버전이 와도 내용을 바꾸지 않아요
    ObjectNode original = withRawVersion(fixture(), 2);
    original.put("eventId", UUID.randomUUID().toString());
    ((ObjectNode) original.path("payload")).put("title", "기준 아닌 출처의 수정");
    ((ObjectNode) original.path("payload").path("notice").path("notice"))
        .put("title", "기준 아닌 출처의 수정");
    assertThat(ingestion.apply(body(original))).isEqualTo(IngestionOutcome.KEPT_BASE_SOURCE);
    assertThat(query.detail(kept).header().title()).isEqualTo(title);
  }

  @Test
  void 합치기를_되돌리면_두_공고가_각자_자기_출처_내용으로_돌아온다() {
    ingestion.apply(body(fixture()));
    UUID kept = onlyNotice();
    String keptTitle = query.detail(kept).header().title();
    String wrongTitle = "서리풀 청년아트타운 잔여세대 모집 (잘못 합쳐진 출처)";
    ObjectNode earlier = postedOn(samePostElsewhere(fixture()), "2026-10-10");
    ((ObjectNode) earlier.path("payload")).put("title", wrongTitle);
    ((ObjectNode) earlier.path("payload").path("notice").path("notice")).put("title", wrongTitle);
    ingestion.apply(body(earlier));
    UUID merged = mergedInto(kept);
    assertThat(query.detail(kept).header().title()).isEqualTo(wrongTitle); // 기준이 바뀌어 있었음
    events.clear();

    ingestion.unmerge(merged);

    assertThat(listed()).hasSize(2);
    assertThat(query.detail(merged).header().id()).isEqualTo(merged); // 다시 따로 보임
    assertThat(query.detail(merged).header().title()).isEqualTo(wrongTitle);
    assertThat(query.detail(kept).header().title()).isEqualTo(keptTitle); // 원래 출처 내용으로 돌아옴
    assertThat(events.stream(NoticeUpdated.class))
        .extracting(NoticeUpdated::noticeId)
        .contains(kept, merged);
    assertThatThrownBy(() -> ingestion.unmerge(merged))
        .isInstanceOf(IllegalArgumentException.class); // 이미 따로인 공고
  }

  @Test
  void 잘못된_합치기는_거절하고_아니라고_표시한_후보는_정리한다() {
    ingestion.apply(body(fixture()));
    UUID first = onlyNotice();
    ingestion.apply(body(otherPost(fixture()))); // 다른 공고(자동으로 합쳐지지 않음)
    UUID second =
        jdbc.sql("select id from notice.notices where id <> :first")
            .param("first", first)
            .query(UUID.class)
            .single();
    // 사람이 확인할 후보(자동으로 합치지 못한 경우)
    jdbc.sql(
            "insert into notice.notice_duplicate_candidates (notice_id, candidate_of, reason,"
                + " status, created_at) values (:a, :b, 'TEST', 'PENDING', now())")
        .param("a", second)
        .param("b", first)
        .update();

    assertThatThrownBy(() -> merges.merge(first, first))
        .isInstanceOf(IllegalArgumentException.class);
    assertThatThrownBy(() -> merges.merge(UUID.randomUUID(), first))
        .isInstanceOf(IllegalArgumentException.class);

    assertThat(merges.reject(second, first)).isTrue();
    assertThat(merges.pendingCandidates()).isEmpty();
    assertThat(merges.reject(second, first)).isFalse();

    merges.merge(second, first);
    assertThatThrownBy(() -> merges.merge(second, first))
        .isInstanceOf(IllegalArgumentException.class);
  }

  // ---------- 판정용 공고 목록 ----------

  @Test
  void 판정용_공고_목록은_마감만_빼고_법정동_10자리_지역과_판정_틀을_준다() {
    ObjectNode withFrame = fixture(); // 서리풀 공고 + 계약 예시의 판정 틀
    ObjectNode frame;
    try (InputStream in =
        getClass()
            .getResourceAsStream("/contracts/tests/fixtures/judgment/housing-examples.json")) {
      frame = (ObjectNode) json.readTree(in).get(0);
    } catch (IOException e) {
      throw new IllegalStateException(e);
    }
    frame.put("rawPostId", withFrame.path("payload").path("rawPostId").asString());
    ((ObjectNode) withFrame.path("payload")).set("judgment", frame);
    ingestion.apply(body(withFrame));
    ingestion.apply(body(otherPost(fixture()))); // 판정 틀 없는 공고
    ingestion.apply(body(otherPost(fixture()))); // 아래에서 마감으로
    ingestion.apply(body(otherPost(fixture()))); // 아래에서 전국 공고로
    List<UUID> ids =
        jdbc.sql("select id from notice.notices order by created_at, id").query(UUID.class).list();
    jdbc.sql("update notice.notices set status = 'CLOSED' where id = :id")
        .param("id", ids.get(2))
        .update();
    jdbc.sql("update notice.notices set nationwide = true where id = :id")
        .param("id", ids.get(3))
        .update();

    List<NoticeForJudgment> open = query.findOpenForJudgment(NoticeField.HOUSING);

    assertThat(open)
        .extracting(NoticeForJudgment::noticeId)
        .containsExactlyInAnyOrder(ids.get(0), ids.get(1), ids.get(3)); // 마감 공고만 빠져요
    NoticeForJudgment first =
        open.stream().filter(n -> n.noticeId().equals(ids.get(0))).findFirst().orElseThrow();
    assertThat(first.version()).isEqualTo(1);
    assertThat(first.applyStart()).isEqualTo(LocalDate.of(2026, 10, 26));
    assertThat(first.applyEnd()).isEqualTo(LocalDate.of(2026, 10, 30));
    assertThat(first.regionCodes()).containsExactly("1165000000");
    assertThat(first.frame().path("schema").asString()).isEqualTo("housing-judgment.v1");
    assertThat(
            open.stream()
                .filter(n -> n.noticeId().equals(ids.get(1)))
                .findFirst()
                .orElseThrow()
                .frame())
        .isNull(); // 판정 틀이 없어도 빼지 않아요
    assertThat(
            open.stream()
                .filter(n -> n.noticeId().equals(ids.get(3)))
                .findFirst()
                .orElseThrow()
                .regionCodes())
        .isEmpty(); // 전국 공고
    assertThat(query.findOpenForJudgment(NoticeField.BUSINESS_SPACE)).isEmpty();
  }

  // ---------- 지역 점수 ----------

  @Test
  void 공개할_때_위치를_area에_알린다() {
    ingestion.apply(body(fixture()));
    UUID id = onlyNotice();

    assertThat(events.stream(NoticeLocationsChanged.class))
        .singleElement()
        .satisfies(
            e -> {
              assertThat(e.noticeId()).isEqualTo(id);
              assertThat(e.noticeVersion()).isEqualTo(1);
              assertThat(e.locations()).isNotEmpty();
              assertThat(e.locations().getFirst().regionCode()).isEqualTo("1165000000");
            });
  }

  @Test
  void area가_계산한_점수를_저장하고_현재_위치의_점수만_보여준다() {
    ingestion.apply(body(fixture()));
    UUID id = onlyNotice();
    String locationId = firstLocation();
    Instant at = Instant.parse("2026-10-19T01:00:00Z");

    int saved =
        areaScores.save(
            new AreaScoresCalculated(
                id,
                1,
                List.of(
                    new AreaScoresCalculated.Score(locationId, "LIVING", 72.5, at, "v1"),
                    new AreaScoresCalculated.Score(locationId, "COMMERCIAL", 101, at, "v1"),
                    new AreaScoresCalculated.Score("old-location", "LIVING", 50, at, "v1"))));

    assertThat(saved).isEqualTo(1); // 현재 위치에 없거나 범위를 넘은 점수는 버려요
    assertThat(query.detail(id).areaSummaries())
        .singleElement()
        .satisfies(
            a -> {
              assertThat(a.siteId()).isEqualTo(locationId);
              assertThat(a.score()).isEqualByComparingTo("72.5");
            });

    areaScores.save( // 늦게 도착한 옛 계산은 덮어쓰지 않아요
        new AreaScoresCalculated(
            id,
            1,
            List.of(
                new AreaScoresCalculated.Score(
                    locationId, "LIVING", 10, at.minusSeconds(60), "v0"))));
    assertThat(query.detail(id).areaSummaries().getFirst().score()).isEqualByComparingTo("72.5");
    assertThat(areaScores.save(new AreaScoresCalculated(UUID.randomUUID(), 1, List.of()))).isZero();
  }

  @Test
  void 같은_위치_ID라도_주소가_바뀌면_이전_버전의_점수를_쓰지_않는다() {
    ingestion.apply(body(fixture()));
    UUID id = onlyNotice();
    var score = new AreaScoresCalculated.Score(firstLocation(), "LIVING", 72.5, START, "v1");
    assertThat(areaScores.save(new AreaScoresCalculated(id, 1, List.of(score)))).isEqualTo(1);
    assertThat(areaScores.save(new AreaScoresCalculated(id, 99, List.of(score)))).isZero();
    ObjectNode changed = withRawVersion(fixture(), 2);
    changed.put("eventId", UUID.randomUUID().toString());
    ((ObjectNode) changed.path("payload").path("notice").path("locations").get(0))
        .put("address", "변경된 주소");
    ingestion.apply(body(changed));
    assertThat(query.detail(id).areaSummaries()).isEmpty();
    assertThat(areaScores.save(new AreaScoresCalculated(id, 1, List.of(score)))).isZero();
    assertThat(areaScores.save(new AreaScoresCalculated(id, 2, List.of(score)))).isEqualTo(1);
    assertThat(query.detail(id).areaSummaries()).hasSize(1);
  }

  @Test
  void 제목만_바뀌었으면_지역_점수를_재사용한다() {
    ingestion.apply(body(fixture()));
    UUID id = onlyNotice();
    var score = new AreaScoresCalculated.Score(firstLocation(), "LIVING", 72.5, START, "v1");
    areaScores.save(new AreaScoresCalculated(id, 1, List.of(score)));
    ObjectNode changed = withRawVersion(fixture(), 2);
    changed.put("eventId", UUID.randomUUID().toString());
    ((ObjectNode) changed.path("payload")).put("title", "바뀐 제목");
    ((ObjectNode) changed.path("payload").path("notice").path("notice")).put("title", "바뀐 제목");
    ingestion.apply(body(changed));
    assertThat(query.detail(id).areaSummaries()).hasSize(1);
    assertThat(areaScores.save(new AreaScoresCalculated(id, 1, List.of(score)))).isEqualTo(1);
    assertThat(events.stream(NoticeLocationsChanged.class)).hasSize(1);
  }

  @Test
  void 지금_버전에서_보류한_위치는_이전_버전의_점수를_보여주지_않는다() {
    ingestion.apply(body(fixture()));
    UUID id = onlyNotice();
    String locationId = firstLocation();
    var score = new AreaScoresCalculated.Score(locationId, "LIVING", 72.5, START, "v1");
    assertThat(areaScores.save(new AreaScoresCalculated(id, 1, List.of(score)))).isEqualTo(1);

    // 위치 내용은 그대로 두고 그 위치의 주소만 보류한 새 버전
    ObjectNode changed = withRawVersion(fixture(), 2);
    changed.put("eventId", UUID.randomUUID().toString());
    ObjectNode payload = (ObjectNode) changed.path("payload");
    JsonNode locations = payload.path("notice").path("locations");
    int index = 0;
    while (!locations.get(index).path("id").asString().equals(locationId)) {
      index++;
    }
    ObjectNode item =
        json.createObjectNode()
            .put("target", "/locations/" + index + "/address")
            .put("extent", "ITEM")
            .put("description", "원문 확인이 필요합니다.");
    item.putArray("codes").add("CHECK");
    ((ArrayNode) payload.path("heldItems")).add(item);
    ((ArrayNode) payload.path("notice").path("quality").path("heldItems")).add(item.deepCopy());
    assertThat(ingestion.apply(body(changed))).isEqualTo(IngestionOutcome.NEW_VERSION);

    assertThat(query.detail(id).areaSummaries()).isEmpty();
    assertThat(areaScores.save(new AreaScoresCalculated(id, 2, List.of(score)))).isZero();
    assertThat(query.detail(id).areaSummaries()).isEmpty();
  }

  private String firstLocation() {
    return events.stream(NoticeLocationsChanged.class)
        .findFirst()
        .orElseThrow()
        .locations()
        .getFirst()
        .locationId();
  }

  // ---------- 보충 발행 ----------

  @Test
  void 보충_발행은_공개_중인_공고만_reprocess로_다시_보낸다() {
    ingestion.apply(body(fixture())); // 접수 예정
    UUID kept = onlyNotice();
    ingestion.apply(body(samePostElsewhere(fixture()))); // 같은 공고 → 자동으로 합쳐짐
    clock.set("2026-11-15T10:00");
    ingestion.apply(body(otherPost(fixture()))); // 처음부터 마감
    events.clear();

    Map<NoticeBackfillService.Kind, Integer> open =
        backfill.republish(
            EnumSet.of(NoticeBackfillService.Kind.PUBLISHED, NoticeBackfillService.Kind.LOCATIONS),
            false,
            1); // 한 건씩 묶어 여러 묶음을 도는지도 확인

    assertThat(open)
        .containsEntry(NoticeBackfillService.Kind.PUBLISHED, 1)
        .containsEntry(NoticeBackfillService.Kind.LOCATIONS, 1);
    assertThat(events.stream(NoticePublished.class))
        .singleElement()
        .satisfies(
            e -> {
              assertThat(e.noticeId()).isEqualTo(kept);
              assertThat(e.reprocess()).isTrue(); // 사용자 알림을 보내지 않아요
              assertThat(e.regionCode()).isEqualTo("11650");
              assertThat(e.regionCodes()).containsExactly("11650");
            });
    assertThat(events.stream(NoticeLocationsChanged.class))
        .singleElement()
        .satisfies(e -> assertThat(e.noticeVersion()).isEqualTo(1));

    Map<NoticeBackfillService.Kind, Integer> all =
        backfill.republish(EnumSet.of(NoticeBackfillService.Kind.PUBLISHED), true, 1);
    assertThat(all).containsEntry(NoticeBackfillService.Kind.PUBLISHED, 2); // 합친 공고는 빠져요
  }

  // ---------- 도우미 ----------

  private ObjectNode load(String name) {
    try (InputStream in = getClass().getResourceAsStream(name)) {
      return (ObjectNode) json.readTree(in);
    } catch (IOException e) {
      throw new IllegalStateException(e);
    }
  }

  private ObjectNode fixture() {
    return load("/notice/extraction-completed-seoripul.json");
  }

  private static ObjectNode withStatus(ObjectNode event, String status) {
    ((ObjectNode) event.path("payload")).put("reviewStatus", status);
    if (status.equals("APPROVED")) {
      ((ObjectNode) event.path("payload")).remove("heldItems");
      ((ObjectNode) event.path("payload").path("notice").path("quality")).remove("heldItems");
      for (JsonNode c : event.path("payload").path("conditions")) {
        ((ObjectNode) c).put("inReview", false).putArray("reviewReasons");
      }
    }
    return event;
  }

  private static ObjectNode withRawVersion(ObjectNode event, int rawVersion) {
    ((ObjectNode) event.path("payload")).put("rawVersion", rawVersion);
    ((ObjectNode) event.path("payload").path("notice").path("input")).put("rawVersion", rawVersion);
    ((ObjectNode) event.path("payload").path("notice").path("sourceReferences").get(0))
        .put("rawVersion", rawVersion);
    return event;
  }

  /** 이 공고를 정정하는 다른 원본 글. 접수 마감일을 바꿔요. */
  private static ObjectNode correctionOf(ObjectNode original, String newApplyEndOn) {
    String originalPostId = original.path("payload").path("rawPostId").asString();
    String correctionPostId = UUID.randomUUID().toString();
    original.put("eventId", UUID.randomUUID().toString());
    ObjectNode payload = (ObjectNode) original.path("payload");
    payload.put("rawPostId", correctionPostId);
    ((ObjectNode) payload.path("notice").path("input")).put("rawPostId", correctionPostId);
    setApplicationEnd(payload, newApplyEndOn);
    ObjectNode reference = (ObjectNode) payload.path("notice").path("sourceReferences").get(0);
    reference.put("rawPostId", correctionPostId);
    reference.put("kind", "CORRECTION");
    reference.put("supersedesPostId", originalPostId);
    return original;
  }

  /** 원래 공고와 보이는 내용이 같은 정정 공고 (일정을 원래 공고 그대로 둬요). */
  private ObjectNode unchangedCorrection() {
    ObjectNode correction = correctionOf(fixture(), "2026-10-30");
    ObjectNode original = (ObjectNode) fixture().path("payload");
    ObjectNode payload = (ObjectNode) correction.path("payload");
    payload.set("schedule", original.path("schedule"));
    payload.set("applicationWindows", original.path("applicationWindows"));
    ((ObjectNode) payload.path("notice"))
        .set("schedules", original.path("notice").path("schedules"));
    return correction;
  }

  /** 접수 마감일을 바꿔요 (원문 일정과 목록용 칸 모두). */
  private static void setApplicationEnd(ObjectNode payload, String end) {
    ((ObjectNode) payload.path("schedule")).put("applyEndOn", end);
    ((ObjectNode) payload.path("applicationWindows").get(0)).put("applyEndOn", end);
    for (JsonNode schedule : payload.path("notice").path("schedules")) {
      if (schedule.path("kinds").toString().contains("APPLICATION")) {
        ((ObjectNode) schedule).putObject("endsAt").put("precision", "DAY").put("value", end);
      }
    }
  }

  private static int round = 1;

  /** 다른 공고: 다른 원본 글에 모집 회차(「N차」)가 다른 공고. */
  private static ObjectNode otherPost(ObjectNode event) {
    String title = event.path("payload").path("title").asString() + " " + (++round) + "차";
    ((ObjectNode) event.path("payload")).put("title", title);
    ((ObjectNode) event.path("payload").path("notice").path("notice")).put("title", title);
    event.put("eventId", UUID.randomUUID().toString());
    String id = UUID.randomUUID().toString();
    ((ObjectNode) event.path("payload")).put("rawPostId", id);
    ((ObjectNode) event.path("payload").path("notice").path("input")).put("rawPostId", id);
    ((ObjectNode) event.path("payload").path("notice").path("sourceReferences").get(0))
        .put("rawPostId", id);
    return event;
  }

  /** 이 지역으로 찾은 공고 목록 (주거, 마감 제외). */
  private List<NoticeSummaryResponse> listIn(String regionCode) {
    return query
        .list(
            new NoticeListFilter(null, List.of(regionCode), null, null, null, null, null),
            null,
            100)
        .items();
  }

  /** 다른 출처에 올라온 같은 공고: 다른 원본 글의 같은 내용. 같은 공고로 판정돼 자동으로 합쳐져요. */
  private static ObjectNode samePostElsewhere(ObjectNode event) {
    event.put("eventId", UUID.randomUUID().toString());
    String id = UUID.randomUUID().toString();
    ((ObjectNode) event.path("payload")).put("rawPostId", id);
    ((ObjectNode) event.path("payload").path("notice").path("input")).put("rawPostId", id);
    ((ObjectNode) event.path("payload").path("notice").path("sourceReferences").get(0))
        .put("rawPostId", id);
    return event;
  }

  /** 공고일을 같은 공고로 보는 기간보다 늦춰요. */
  private static ObjectNode announcedLater(ObjectNode event) {
    ObjectNode notice = (ObjectNode) event.path("payload").path("notice").path("notice");
    notice.put(
        "announcedOn",
        LocalDate.parse(notice.path("announcedOn").asString())
            .plusDays(DuplicateRule.WINDOW_DAYS + 1)
            .toString());
    return event;
  }

  /** kept에 합쳐진 공고 하나. */
  private UUID mergedInto(UUID kept) {
    return jdbc.sql("select id from notice.notices where merged_into = :kept")
        .param("kept", kept)
        .query(UUID.class)
        .single();
  }

  /** 목록에 나오는(다른 공고에 합쳐지지 않은) 공고. */
  private List<UUID> listed() {
    return jdbc.sql("select id from notice.notices where merged_into is null")
        .query(UUID.class)
        .list();
  }

  private String statusOf(UUID id) {
    return query.detail(id).header().status();
  }

  /** 원본 글 게시일을 바꿔요. */
  private static ObjectNode postedOn(ObjectNode event, String day) {
    ((ObjectNode) event.path("payload").path("notice").path("sourceReferences").get(0))
        .put("postedOn", day);
    return event;
  }

  /** 이 공고의 후속 안내 글 (원문 제목을 바꿔요). */
  private static ObjectNode followUpOf(ObjectNode original, String title) {
    ObjectNode followUp = correctionOf(original, "2026-10-30");
    ObjectNode reference =
        (ObjectNode) followUp.path("payload").path("notice").path("sourceReferences").get(0);
    reference.put("kind", "FOLLOW_UP");
    reference.put("sourceTitle", title);
    return followUp;
  }

  private String body(ObjectNode event) {
    return json.writeValueAsString(event);
  }

  private UUID onlyNotice() {
    List<UUID> ids = listed();
    assertThat(ids).hasSize(1);
    return ids.getFirst();
  }

  private long count(String table) {
    return jdbc.sql("select count(*) from " + table).query(Long.class).single();
  }

  private List<String> outcomes() {
    return jdbc.sql(
            "select outcome || coalesce(':' || reason, '') from notice.extraction_results"
                + " order by received_at")
        .query(String.class)
        .list();
  }
}
