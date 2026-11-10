package kr.mujuthaek.api.notice.client;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.content;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.header;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withServerError;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withStatus;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

import java.time.Duration;
import kr.mujuthaek.api.common.exception.CustomException;
import kr.mujuthaek.api.common.exception.ErrorCode;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;

/** 가짜 검수 API로 요청 모양과 오류 바꾸기를 봐요. */
class ExtractionReviewClientTest {

  private static final String BASE = "http://extraction.test:8092";
  private static final String JOB = "6f1c2a6b-9d10-4f41-9d7e-3f1c2a6b9d10";
  private MockRestServiceServer server;

  private ExtractionReviewClient client(String token) {
    var builder = RestClient.builder();
    server = MockRestServiceServer.bindTo(builder).build();
    return new ExtractionReviewClient(
        new ExtractionReviewProperties(BASE, token, Duration.ofSeconds(1)), builder);
  }

  @Test
  void listSendsTokenAndReturnsItems() {
    var client = client("test-token");
    server
        .expect(requestTo(BASE + "/reviews?status=PENDING&limit=1000"))
        .andExpect(header("Authorization", "Bearer test-token"))
        .andRespond(
            withSuccess("{\"items\":[{\"jobId\":\"" + JOB + "\"}]}", MediaType.APPLICATION_JSON));
    assertThat(client.list("PENDING").get(0).get("jobId").asString()).isEqualTo(JOB);
    server.verify();
  }

  @Test
  void noTokenSendsNoAuthorization() {
    var client = client("");
    server
        .expect(requestTo(BASE + "/reviews?status=PENDING&limit=1000"))
        .andExpect(
            request -> assertThat(request.getHeaders().containsHeader("Authorization")).isFalse())
        .andRespond(withSuccess("{\"items\":[]}", MediaType.APPLICATION_JSON));
    assertThat(client.list("PENDING")).isEmpty();
  }

  @Test
  void rejectPostsNote() {
    var client = client(null);
    server
        .expect(requestTo(BASE + "/reviews/" + JOB + "/reject"))
        .andExpect(method(HttpMethod.POST))
        .andExpect(content().json("{\"note\":\"[중복 공고]\"}"))
        .andRespond(withSuccess("{\"reviewStatus\":\"REJECTED\"}", MediaType.APPLICATION_JSON));
    assertThat(client.reject(JOB, "[중복 공고]", null).get("reviewStatus").asString())
        .isEqualTo("REJECTED");
  }

  @Test
  void conflictKeepsUpstreamExplanation() {
    var client = client(null);
    server
        .expect(requestTo(BASE + "/reviews/" + JOB + "/approve"))
        .andRespond(
            withStatus(HttpStatus.CONFLICT)
                .contentType(MediaType.APPLICATION_JSON)
                .body("{\"error\":\"이미 APPROVED 처리된 항목입니다.\"}"));
    assertThatThrownBy(() -> client.approve(JOB, null, null, null))
        .isInstanceOfSatisfying(
            CustomException.class,
            e -> {
              assertThat(e.errorCode()).isEqualTo(ErrorCode.NOTICE_REVIEW_CONFLICT);
              assertThat(e.getMessage()).isEqualTo("이미 APPROVED 처리된 항목입니다.");
            });
  }

  @Test
  void notFoundAndInvalidAreMapped() {
    var client = client(null);
    server.expect(requestTo(BASE + "/reviews/" + JOB)).andRespond(withStatus(HttpStatus.NOT_FOUND));
    assertThatThrownBy(() -> client.detail(JOB))
        .isInstanceOfSatisfying(
            CustomException.class,
            e -> assertThat(e.errorCode()).isEqualTo(ErrorCode.NOTICE_REVIEW_NOT_FOUND));
  }

  @Test
  void serverErrorAndAuthFailureAreUnavailable() {
    var client = client(null);
    server
        .expect(requestTo(BASE + "/reviews?status=PENDING&limit=1000"))
        .andRespond(withServerError());
    assertThatThrownBy(() -> client.list("PENDING"))
        .isInstanceOfSatisfying(
            CustomException.class,
            e -> assertThat(e.errorCode()).isEqualTo(ErrorCode.NOTICE_REVIEW_UNAVAILABLE));
    server.reset();
    server
        .expect(requestTo(BASE + "/reviews?status=PENDING&limit=1000"))
        .andRespond(withStatus(HttpStatus.UNAUTHORIZED));
    assertThatThrownBy(() -> client.list("PENDING"))
        .isInstanceOfSatisfying(
            CustomException.class,
            e -> assertThat(e.errorCode()).isEqualTo(ErrorCode.NOTICE_REVIEW_UNAVAILABLE));
  }

  @Test
  void realClientSendsContentLengthNotChunked() throws Exception {
    // 2026-10-25 로컬 실제 흐름: 조각 전송(chunked)이면 파이썬 검수 API가 본문을 빈 것으로 읽어 승인·반려·다시 열기가 400이 됐어요
    var seen = new java.util.concurrent.atomic.AtomicReference<String>();
    var http =
        com.sun.net.httpserver.HttpServer.create(new java.net.InetSocketAddress("127.0.0.1", 0), 0);
    http.createContext(
        "/",
        exchange -> {
          seen.set(
              exchange.getRequestHeaders().getFirst("Content-Length")
                  + "|"
                  + exchange.getRequestHeaders().getFirst("Transfer-Encoding"));
          exchange.getRequestBody().readAllBytes();
          byte[] reply = "{\"reviewStatus\":\"REJECTED\"}".getBytes();
          exchange.getResponseHeaders().add("Content-Type", "application/json");
          exchange.sendResponseHeaders(200, reply.length);
          exchange.getResponseBody().write(reply);
          exchange.close();
        });
    http.start();
    try {
      var client =
          new ExtractionReviewClient(
              new ExtractionReviewProperties(
                  "http://127.0.0.1:" + http.getAddress().getPort(), null, Duration.ofSeconds(2)));
      client.reject(JOB, "메모", "admin-1");
      assertThat(seen.get()).doesNotEndWith("|chunked").doesNotStartWith("null|");
    } finally {
      http.stop(0);
    }
  }
}
