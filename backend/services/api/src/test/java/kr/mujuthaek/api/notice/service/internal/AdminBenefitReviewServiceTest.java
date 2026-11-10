package kr.mujuthaek.api.notice.service.internal;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.content;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withStatus;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

import java.time.Duration;
import java.util.List;
import kr.mujuthaek.api.common.exception.CustomException;
import kr.mujuthaek.api.common.exception.ErrorCode;
import kr.mujuthaek.api.notice.client.ExtractionReviewClient;
import kr.mujuthaek.api.notice.client.ExtractionReviewProperties;
import kr.mujuthaek.api.notice.dto.request.AdminReviewDecisionRequest;
import kr.mujuthaek.api.notice.dto.request.AdminReviewDecisionRequest.FieldEdit;
import kr.mujuthaek.api.notice.dto.request.AdminReviewDecisionRequest.RejectReason;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.ExpectedCount;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;
import tools.jackson.databind.node.JsonNodeFactory;

/** 가짜 추출 검수 API로 관리자 혜택 검수 대행(목록·상세·승인·반려)을 봐요. */
class AdminBenefitReviewServiceTest {

  private static final String BASE = "http://extraction.test:8092";
  private static final String REVIEW = "01929a3e-0000-7000-8000-0000000b0a01";
  private static final String POLICY = "01929a3e-0000-7000-8000-0000000b0001";
  private static final String ITEM =
      "{\"reviewId\":\""
          + REVIEW
          + "\",\"rawPolicyId\":\""
          + POLICY
          + "\",\"rawVersion\":2,\"sourceCode\":\"youth\",\"policyId\":\"2026001\","
          + "\"title\":\"가상 청년 월세\",\"reviewStatus\":\"PENDING\","
          + "\"reasons\":[\"LOW_CONFIDENCE\",\"REPORTED\"],\"queuedAt\":\"2026-10-25 03:00:00+00:00\","
          + "\"decidedAt\":null,\"applyEndsOn\":\"2026-11-30\",\"relevant\":true,\"reported\":true}";

  private MockRestServiceServer server;
  private AdminBenefitReviewService service;

  @BeforeEach
  void setUp() {
    var builder = RestClient.builder();
    server = MockRestServiceServer.bindTo(builder).build();
    service =
        new AdminBenefitReviewService(
            new ExtractionReviewClient(
                new ExtractionReviewProperties(BASE, "t", Duration.ofSeconds(1)), builder),
            java.time.Clock.fixed(
                java.time.Instant.parse("2026-10-25T03:00:00Z"), java.time.ZoneOffset.UTC));
  }

  @Test
  void countsUseTheTotalWithoutTheWholeList() {
    server
        .expect(requestTo(BASE + "/benefit-reviews?status=PENDING&limit=1"))
        .andRespond(
            withSuccess("{\"total\":1500,\"items\":[" + ITEM + "]}", MediaType.APPLICATION_JSON));
    assertThat(service.counts().benefitPending()).isEqualTo(1500);
    server.verify();
  }

  @Test
  void countsAreReusedBrieflyAndRefetchedAfterADecision() {
    // 받을 요청 차례: 건수 → 반려 → 남은 건수 → (처리했으니) 건수 다시. 더 받으면 가짜 서버가 실패시켜요
    server
        .expect(requestTo(BASE + "/benefit-reviews?status=PENDING&limit=1"))
        .andRespond(withSuccess("{\"total\":2,\"items\":[]}", MediaType.APPLICATION_JSON));
    server
        .expect(requestTo(BASE + "/benefit-reviews/" + REVIEW + "/reject"))
        .andRespond(withSuccess("{\"reviewStatus\":\"REJECTED\"}", MediaType.APPLICATION_JSON));
    server
        .expect(ExpectedCount.times(2), requestTo(BASE + "/benefit-reviews?status=PENDING&limit=1"))
        .andRespond(withSuccess("{\"total\":1,\"items\":[]}", MediaType.APPLICATION_JSON));

    assertThat(service.counts().benefitPending()).isEqualTo(2);
    assertThat(service.counts().benefitPending()).isEqualTo(2);
    service.reject(REVIEW, null, "admin-1");
    assertThat(service.counts().benefitPending()).isEqualTo(1);
    server.verify();
  }

  @Test
  void detailKeepsTheResultAndTheSourceText() {
    server
        .expect(requestTo(BASE + "/benefit-reviews/" + REVIEW))
        .andRespond(
            withSuccess(
                "{\"reviewId\":\""
                    + REVIEW
                    + "\",\"rawPolicyId\":\""
                    + POLICY
                    + "\",\"rawVersion\":2,\"reviewStatus\":\"PENDING\",\"reasons\":[],"
                    + "\"queuedAt\":\"2026-10-25 03:00:00+00:00\",\"edits\":null,"
                    + "\"payload\":{\"summary\":\"요약\",\"conditions\":[]},"
                    + "\"source\":{\"title\":\"가상 청년 월세\",\"text\":\"원문\",\"categories\":[\"주거\"]}}",
                MediaType.APPLICATION_JSON));
    var detail = service.detail(REVIEW);
    assertThat(detail.result().get("summary").asString()).isEqualTo("요약");
    assertThat(detail.source().text()).isEqualTo("원문");
    assertThat(detail.source().categories()).containsExactly("주거");
    assertThat(detail.edits()).isNull();
  }

  @Test
  void approveSendsEditsAndReturnsTheRemainingCount() {
    server
        .expect(requestTo(BASE + "/benefit-reviews/" + REVIEW + "/approve"))
        .andExpect(method(HttpMethod.POST))
        .andExpect(
            content()
                .json(
                    "{\"note\":\"확인\",\"reviewer\":\"admin-1\","
                        + "\"edits\":[{\"path\":\"/summary\",\"value\":\"고친 요약\"}]}"))
        .andRespond(withSuccess("{\"reviewStatus\":\"APPROVED\"}", MediaType.APPLICATION_JSON));
    server
        .expect(requestTo(BASE + "/benefit-reviews?status=PENDING&limit=1"))
        .andRespond(withSuccess("{\"items\":[]}", MediaType.APPLICATION_JSON));
    var edit = new FieldEdit("/summary", JsonNodeFactory.instance.stringNode("고친 요약"));
    var result =
        service.approve(
            REVIEW, new AdminReviewDecisionRequest(null, "확인", List.of(edit)), "admin-1");
    assertThat(result.reviewStatus()).isEqualTo("APPROVED");
    assertThat(result.pendingCount()).isZero();
    server.verify();
  }

  @Test
  void rejectPutsTheReasonInFrontOfTheNote() {
    server
        .expect(requestTo(BASE + "/benefit-reviews/" + REVIEW + "/reject"))
        .andExpect(content().json("{\"note\":\"[서비스 대상 아님] 주거 지원 아님\"}"))
        .andRespond(withSuccess("{\"reviewStatus\":\"REJECTED\"}", MediaType.APPLICATION_JSON));
    server
        .expect(requestTo(BASE + "/benefit-reviews?status=PENDING&limit=1"))
        .andRespond(withSuccess("{\"items\":[" + ITEM + "]}", MediaType.APPLICATION_JSON));
    var result =
        service.reject(
            REVIEW,
            new AdminReviewDecisionRequest(RejectReason.OUT_OF_SCOPE, "주거 지원 아님", null),
            null);
    assertThat(result.pendingCount()).isEqualTo(1);
  }

  @Test
  void alreadyDecidedIsAConflict() {
    server
        .expect(requestTo(BASE + "/benefit-reviews/" + REVIEW + "/approve"))
        .andRespond(
            withStatus(HttpStatus.CONFLICT)
                .contentType(MediaType.APPLICATION_JSON)
                .body("{\"error\":\"이미 APPROVED 처리된 항목입니다.\"}"));
    assertThatThrownBy(() -> service.approve(REVIEW, null, null))
        .isInstanceOf(CustomException.class)
        .extracting(e -> ((CustomException) e).errorCode())
        .isEqualTo(ErrorCode.NOTICE_REVIEW_CONFLICT);
  }
}
