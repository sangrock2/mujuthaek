package kr.mujuthaek.api.notice.service.internal;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.content;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

import java.time.Duration;
import java.time.OffsetDateTime;
import kr.mujuthaek.api.common.exception.CustomException;
import kr.mujuthaek.api.notice.client.ExtractionReviewClient;
import kr.mujuthaek.api.notice.client.ExtractionReviewProperties;
import kr.mujuthaek.api.notice.dto.request.AdminReviewDecisionRequest;
import kr.mujuthaek.api.notice.dto.request.AdminReviewDecisionRequest.RejectReason;
import kr.mujuthaek.api.notice.dto.response.AdminReviewDetailResponse.Issue;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.ExpectedCount;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;
import tools.jackson.databind.json.JsonMapper;

/** 검수 API 응답을 관리자 화면 모양으로 옮기는 규칙. 가짜 검수 API를 써요. */
class AdminReviewServiceTest {

  private static final String BASE = "http://extraction.test";
  private static final String A = "11111111-1111-1111-1111-111111111111";
  private static final String B = "22222222-2222-2222-2222-222222222222";
  private static final String C = "33333333-3333-3333-3333-333333333333";
  private static final String LIST =
      """
      {"items":[
        {"jobId":"%s","jobStatus":"IN_REVIEW","reviewStatus":"PENDING","title":"가상 행복주택",
         "sourceTitle":"가상 글","sourceCode":"lh_myhome","rawVersion":2,
         "queuedAt":"2026-10-24 21:00:00.5+00:00","applyEndsOn":"2026-10-27","reasons":["VALUE_NOT_IN_QUOTE /eligibility/3/value","VALUE_NOT_IN_QUOTE /eligibility/3/value","EVIDENCE_SCATTERED /eligibility/4"]},
        {"jobId":"%s","jobStatus":"PARTIAL","reviewStatus":"PENDING","title":null,
         "sourceTitle":"가상 국민임대","sourceCode":"sh_board","rawVersion":1,
         "queuedAt":"2026-10-25T01:00:00+00:00","applyEndsOn":"2026-10-24","reasons":["SUPPLY_PRICE_MISSING"]},
        {"jobId":"%s","jobStatus":"INTAKE_REVIEW","reviewStatus":"PENDING","title":null,
         "sourceTitle":"가상 장기전세","sourceCode":"sh_board","rawVersion":1,
         "queuedAt":"2026-10-25T02:00:00+00:00","applyEndsOn":"2026-11-30","reasons":[]}
      ]}
      """
          .formatted(A, B, C);

  private MockRestServiceServer server;

  private AdminReviewService service() {
    var builder = RestClient.builder();
    server = MockRestServiceServer.bindTo(builder).build();
    var client =
        new ExtractionReviewClient(
            new ExtractionReviewProperties(BASE, null, Duration.ofSeconds(1)), builder);
    return new AdminReviewService(
        client,
        java.time.Clock.fixed(
            java.time.Instant.parse("2026-10-25T03:00:00Z"), java.time.ZoneOffset.UTC));
  }

  private void expectList(int times) {
    server
        .expect(ExpectedCount.times(times), requestTo(BASE + "/reviews?status=PENDING&limit=1000"))
        .andRespond(withSuccess(LIST, MediaType.APPLICATION_JSON));
  }

  /** 건수·남은 건수: 가장 오래된 한 건과 전체 건수만 받아요. */
  private void expectHead() {
    server
        .expect(requestTo(BASE + "/reviews?status=PENDING&limit=1"))
        .andRespond(
            withSuccess(
                """
                {"total":3,"items":[{"jobId":"%s","jobStatus":"IN_REVIEW","reviewStatus":"PENDING",
                 "title":"가상 행복주택","queuedAt":"2026-10-24 21:00:00.5+00:00","reasons":[]}]}
                """
                    .formatted(A),
                MediaType.APPLICATION_JSON));
  }

  @Test
  void countsUseTheTotalNotTheTruncatedListLength() {
    var service = service();
    server
        .expect(requestTo(BASE + "/reviews?status=PENDING&limit=1"))
        .andRespond(
            withSuccess(
                """
                {"total":1200,"items":[{"jobId":"%s","jobStatus":"IN_REVIEW","reasons":[],
                 "queuedAt":"2026-10-24 21:00:00+00:00","title":"가상 공고"}]}
                """
                    .formatted(A),
                MediaType.APPLICATION_JSON));
    assertThat(service.counts().reviewPending()).isEqualTo(1200);
  }

  @Test
  void itemsGroupReasonsByJobStatusAndFallBackToSourceTitle() {
    // 목록 항목 만들기(사유 묶음·제목 대신 원문 제목·이슈 수)는 급한 검수로 확인해요 (대기 전체 목록 API는 2026-10-30에 지웠어요)
    var service = service();
    expectList(1);
    var items = service.urgent(30);
    assertThat(items)
        .extracting(i -> i.reason() + " " + i.title() + " " + i.issueCount())
        .containsExactly("CHECK 가상 국민임대 1", "MUST 가상 행복주택 2");
    assertThat(items.get(1).receivedAt()).isEqualTo(OffsetDateTime.parse("2026-10-24T21:00:00.5Z"));
  }

  @Test
  void countsGivesPendingAndOldest() {
    var service = service();
    expectHead();
    var counts = service.counts();
    assertThat(counts.reviewPending()).isEqualTo(3);
    assertThat(counts.oldestReceivedAt()).isEqualTo(OffsetDateTime.parse("2026-10-24T21:00:00.5Z"));
  }

  @Test
  void countsAreReusedBrieflyAndRefetchedAfterADecision() {
    var service = service();
    // 받을 요청 차례: 건수 → 반려 → 남은 건수 → (처리했으니) 건수 다시. 더 받으면 가짜 서버가 실패시켜요
    expectHead();
    server
        .expect(requestTo(BASE + "/reviews/" + B + "/reject"))
        .andRespond(withSuccess("{\"reviewStatus\":\"REJECTED\"}", MediaType.APPLICATION_JSON));
    expectHead();
    expectHead();

    var first = service.counts();
    assertThat(service.counts()).isSameAs(first);
    service.reject(B, null, "admin-1");
    assertThat(service.counts()).isNotSameAs(first);
    server.verify();
  }

  @Test
  void detailUsesCandidateTitleAndRawEvent() {
    var service = service();
    server
        .expect(requestTo(BASE + "/reviews/" + A))
        .andRespond(
            withSuccess(
                """
                {"jobId":"%s","jobStatus":"IN_REVIEW","reviewStatus":"REJECTED","note":"[중복 공고]",
                 "reasons":["CRITERION_NOT_STRUCTURED /eligibility/10"],"decidedAt":"2026-10-25 03:00:00+00:00",
                 "rawPostId":"44444444-4444-4444-4444-444444444444",
                 "candidate":{"notice":{"title":"가상 행복주택 모집"}},
                 "rawEvent":{"occurredAt":"2026-10-24T20:00:00Z","payload":{"field":"HOUSING","provider":"LH","sourceCode":"lh_myhome","version":2,"title":"가상 글","detailUrl":"https://example.test/notice/1"}}}
                """
                    .formatted(A),
                MediaType.APPLICATION_JSON));
    var detail = service.detail(A);
    assertThat(detail.title()).isEqualTo("가상 행복주택 모집");
    assertThat(detail.reason()).isEqualTo("MUST");
    assertThat(detail.provider()).isEqualTo("LH");
    assertThat(detail.rawVersion()).isEqualTo(2);
    assertThat(detail.detailUrl()).isEqualTo("https://example.test/notice/1");
    assertThat(detail.issues())
        .containsExactly(new Issue("CRITERION_NOT_STRUCTURED", "/eligibility/10"));
    assertThat(detail.log())
        .extracting(l -> l.who() + " " + l.text())
        .containsExactly("시스템 검수 대기열에 추가", "검수자 반려");
  }

  @Test
  void rejectPutsReasonLabelBeforeNoteAndReturnsRemaining() {
    var service = service();
    server
        .expect(requestTo(BASE + "/reviews/" + B + "/reject"))
        .andExpect(
            content().json("{\"note\":\"[원문과 다름 · 다시 추출] 표가 잘렸어요\",\"reviewer\":\"admin-1\"}"))
        .andRespond(withSuccess("{\"reviewStatus\":\"REJECTED\"}", MediaType.APPLICATION_JSON));
    expectHead();
    var result =
        service.reject(
            B,
            new AdminReviewDecisionRequest(RejectReason.SOURCE_MISMATCH, " 표가 잘렸어요 ", null),
            "admin-1");
    assertThat(result.reviewStatus()).isEqualTo("REJECTED");
    assertThat(result.pendingCount()).isEqualTo(3);
  }

  @Test
  void issuesAcceptObjectsAndSkipBlanks() {
    var reasons =
        JsonMapper.builder()
            .build()
            .readTree("[{\"code\":\"A\",\"target\":\"/x\"},\"\",\"B\",\"B\"]");
    assertThat(AdminReviewService.issues(reasons))
        .containsExactly(new Issue("A", "/x"), new Issue("B", null));
  }

  @Test
  void rejectNoteWithoutReasonOrNote() {
    assertThat(AdminReviewService.rejectNote(null)).isNull();
    assertThat(AdminReviewService.rejectNote(new AdminReviewDecisionRequest(null, "  ", null)))
        .isNull();
    assertThat(
            AdminReviewService.rejectNote(
                new AdminReviewDecisionRequest(RejectReason.CLOSED, null, null)))
        .isEqualTo("[마감된 공고]");
  }

  private static final String DETAIL =
      """
      {"jobId":"%s","jobStatus":"PARTIAL","reviewStatus":"APPROVED","note":null,
       "reasons":["EVIDENCE_SCATTERED"],"queuedAt":"2026-10-25T01:00:00+00:00",
       "decidedAt":"2026-10-25T02:00:00+00:00","decidedBy":"admin-7","edited":true,
       "edits":[{"path":"/eligibility/1/description","before":"가상 옛 설명","after":"가상 새 설명"}],
       "candidate":{"notice":{"title":"가상 공고"},
         "eligibility":[
           {"id":"elig-a","description":"가상 나이 조건","evidenceIds":["ev-2"]},
           {"id":"elig-b","description":"가상 소득 조건","evidenceIds":["ev-1","ev-9"]}],
         "schedules":[{"id":"s1","rawLabel":"가상 접수","evidenceIds":["ev-3"]}],
         "evidence":[
           {"id":"ev-1","locator":{"page":4},"quote":"가상 소득 120%% 이하"},
           {"id":"ev-2","locator":{"page":2},"quote":"가상 만 19세 이상"},
           {"id":"ev-3","quote":"가상 접수 기간"}],
         "quality":{
           "heldItems":[{"target":"/eligibility","codes":["COVERAGE_PARTIAL"],"description":"확인 전까지 판정·화면에 쓰지 않습니다"}],
           "reviewIssues":[
             {"code":"VALUE_NOT_IN_QUOTE","target":"/eligibility/1/description","description":"가상 값이 인용에 없음"},
             {"code":"EVIDENCE_SCATTERED","target":"/schedules/0","description":"가상 근거가 흩어짐"},
             {"code":"EVIDENCE_SCATTERED","target":"/schedules/0","description":"가상 근거가 흩어짐"},
             {"code":"X","target":"/quality/coverage","description":"공고 바깥 기록"},
             {"code":"Y","target":"/eligibility/9","description":"없는 칸"}]}},
       "rawEvent":{"payload":{"field":"HOUSING","sourceCode":"lh_myhome","version":1}}}
      """
          .formatted(A);

  @Test
  void detailListsFieldsWithReasonsInsteadOfConfidence() {
    var service = service();
    server
        .expect(requestTo(BASE + "/reviews/" + A))
        .andRespond(withSuccess(DETAIL, MediaType.APPLICATION_JSON));
    var detail = service.detail(A);
    assertThat(detail.fields())
        .extracting(f -> f.path() + " " + f.status())
        .containsExactly(
            "/eligibility HELD", "/eligibility/1/description HELD", "/schedules/0 CHECK");
    var income = detail.fields().get(1);
    assertThat(income.label()).isEqualTo("자격 조건 · 가상 소득 조건 · description");
    assertThat(income.value().asString()).isEqualTo("가상 소득 조건");
    assertThat(income.editable()).isTrue();
    assertThat(income.reasons()).containsExactly("가상 값이 인용에 없음");
    assertThat(income.sourceIds()).containsExactly("ev-1");
    var schedule = detail.fields().get(2);
    assertThat(schedule.value()).isNull();
    assertThat(schedule.editable()).isFalse();
    assertThat(schedule.display()).isEqualTo("가상 접수");
    assertThat(schedule.reasons()).containsExactly("가상 근거가 흩어짐");
    assertThat(detail.sources())
        .extracting(s -> s.id() + "@" + s.page())
        .containsExactly("ev-1@4", "ev-3@null");
    assertThat(detail.decidedBy()).isEqualTo("admin-7");
    assertThat(detail.edits()).hasSize(1);
    assertThat(detail.log())
        .extracting(l -> l.who() + " " + l.text())
        .containsExactly("시스템 검수 대기열에 추가", "admin-7 1칸 고쳐서 승인");
  }

  @Test
  void approveSendsFieldEditsAndReviewer() throws Exception {
    var service = service();
    var mapper = JsonMapper.builder().build();
    server
        .expect(requestTo(BASE + "/reviews/" + A + "/approve"))
        .andExpect(
            content()
                .json(
                    "{\"note\":\"원문 4쪽\",\"reviewer\":\"admin-7\",\"edits\":[{\"path\":\"/eligibility/1/description\",\"value\":\"가상 새 설명\"}]}"))
        .andRespond(withSuccess("{\"reviewStatus\":\"APPROVED\"}", MediaType.APPLICATION_JSON));
    expectHead();
    var request =
        new AdminReviewDecisionRequest(
            null,
            "원문 4쪽",
            java.util.List.of(
                new AdminReviewDecisionRequest.FieldEdit(
                    "/eligibility/1/description", mapper.readTree("\"가상 새 설명\""))));
    assertThat(service.approve(A, request, "admin-7").reviewStatus()).isEqualTo("APPROVED");
    server.verify();
  }

  @Test
  void statsAddsRates() {
    var service = service();
    server
        .expect(requestTo(BASE + "/reviews/stats?days=7"))
        .andRespond(
            withSuccess(
                "{\"days\":7,\"recent\":{\"approved\":8,\"editedApproved\":1,\"rejected\":1,\"medianMinutes\":240},"
                    + "\"today\":{\"approved\":0,\"editedApproved\":0,\"rejected\":0,\"medianMinutes\":null}}",
                MediaType.APPLICATION_JSON));
    var stats = service.stats(7);
    assertThat(stats.recent().asIsRate()).isEqualTo(80);
    assertThat(stats.recent().editedRate()).isEqualTo(10);
    assertThat(stats.recent().medianMinutes()).isEqualTo(240);
    assertThat(stats.today().asIsRate()).isNull();
    assertThatThrownBy(() -> service.stats(0)).isInstanceOf(CustomException.class);
  }

  @Test
  void urgentKeepsPendingWithDeadlineWithinDaysOrPastSortedByDeadline() {
    var service = service();
    expectList(1);
    assertThat(service.urgent(3))
        .extracting(i -> i.id() + " " + i.applyEndsOn())
        .containsExactly(B + " 2026-10-24", A + " 2026-10-27");
    assertThatThrownBy(() -> service.urgent(31)).isInstanceOf(CustomException.class);
  }

  @Test
  void urgentIsReusedForAMinuteAndRecomputedAfterADecision() {
    var service = service();
    // 받을 요청 차례: 목록 한 번 → 반려 → 남은 건수 → (처리했으니) 목록 다시. 더 받으면 가짜 서버가 실패시켜요
    expectList(1);
    server
        .expect(requestTo(BASE + "/reviews/" + B + "/reject"))
        .andRespond(withSuccess("{\"reviewStatus\":\"REJECTED\"}", MediaType.APPLICATION_JSON));
    expectHead();
    expectList(1);

    var first = service.urgent(3);
    assertThat(service.urgent(3)).isSameAs(first);
    service.reject(B, null, "admin-1");
    assertThat(service.urgent(3)).isNotSameAs(first);
    server.verify();
  }

  @Test
  void impactExplainsWhatApprovalChangesInsteadOfCountingPeople() {
    var mapper = JsonMapper.builder().build();
    var candidate = mapper.readTree("{}");
    var held =
        java.util.List.of(
            new kr.mujuthaek.api.notice.dto.response.AdminReviewDetailResponse.Field(
                "/eligibility",
                "자격 조건",
                "자격 조건",
                "HELD",
                null,
                "",
                false,
                java.util.List.of(),
                java.util.List.of(),
                java.util.List.of()));
    assertThat(AdminReviewService.impact("PENDING", "IN_REVIEW", candidate, java.util.List.of()))
        .startsWith("아직 발행 전인 공고예요");
    assertThat(AdminReviewService.impact("PENDING", "PARTIAL", candidate, held)).contains("보류한 1칸");
    assertThat(
            AdminReviewService.impact(
                "PENDING", "INTAKE_REVIEW", mapper.missingNode(), java.util.List.of()))
        .startsWith("추출 결과가 없어");
    assertThat(AdminReviewService.impact("APPROVED", "IN_REVIEW", candidate, java.util.List.of()))
        .isNull();
    // 제보로 다시 연 건(이미 발행된 결과)은 「발행 전」이 아니에요
    assertThat(AdminReviewService.impact("PENDING", "APPROVED", candidate, java.util.List.of()))
        .startsWith("이미 사용자에게 보이는 공고예요");
  }
}
