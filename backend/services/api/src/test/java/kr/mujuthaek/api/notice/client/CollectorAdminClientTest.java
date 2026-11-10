package kr.mujuthaek.api.notice.client;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
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

/** 가짜 수집기 관리자 API로 요청 모양과 오류 바꾸기를 봐요. */
class CollectorAdminClientTest {

  private static final String BASE = "http://collector.test:8093";
  private MockRestServiceServer server;

  private CollectorAdminClient client(String token) {
    var builder = RestClient.builder();
    server = MockRestServiceServer.bindTo(builder).build();
    return new CollectorAdminClient(
        new CollectorAdminClient.Properties(BASE, token, Duration.ofSeconds(1)), builder);
  }

  @Test
  void sourcesSendsTokenAndPassesBodyThrough() {
    var client = client("t0ken");
    server
        .expect(requestTo(BASE + "/sources"))
        .andExpect(header("Authorization", "Bearer t0ken"))
        .andRespond(
            withSuccess(
                "{\"summary\":{\"ok\":1},\"sources\":[{\"code\":\"sh\",\"state\":\"ok\"}]}",
                MediaType.APPLICATION_JSON));
    assertThat(client.sources().path("sources").get(0).path("code").asString()).isEqualTo("sh");
  }

  @Test
  void pauseAndResumePostToTheRightPath() {
    var client = client(null);
    server
        .expect(requestTo(BASE + "/sources/gh/pause"))
        .andExpect(method(HttpMethod.POST))
        .andRespond(withSuccess("{\"code\":\"gh\",\"enabled\":false}", MediaType.APPLICATION_JSON));
    server
        .expect(requestTo(BASE + "/sources/gh/resume"))
        .andRespond(withSuccess("{\"code\":\"gh\",\"enabled\":true}", MediaType.APPLICATION_JSON));
    assertThat(client.setEnabled("gh", false).path("enabled").asBoolean()).isFalse();
    assertThat(client.setEnabled("gh", true).path("enabled").asBoolean()).isTrue();
    server.verify();
  }

  @Test
  void unknownSourceAndDownCollectorAreMapped() {
    var client = client(null);
    server
        .expect(requestTo(BASE + "/sources/nope/pause"))
        .andRespond(withStatus(HttpStatus.NOT_FOUND));
    assertThatThrownBy(() -> client.setEnabled("nope", false))
        .isInstanceOfSatisfying(
            CustomException.class, e -> assertThat(e.errorCode()).isEqualTo(ErrorCode.NOT_FOUND));
    server.reset();
    server.expect(requestTo(BASE + "/sources")).andRespond(withServerError());
    assertThatThrownBy(client::sources)
        .isInstanceOfSatisfying(
            CustomException.class,
            e -> assertThat(e.errorCode()).isEqualTo(ErrorCode.NOTICE_COLLECTOR_UNAVAILABLE));
  }

  @Test
  void runNowPassesConflictExplanation() {
    var client = client(null);
    server
        .expect(requestTo(BASE + "/sources/sh/run"))
        .andExpect(method(HttpMethod.POST))
        .andRespond(
            withStatus(HttpStatus.ACCEPTED)
                .contentType(MediaType.APPLICATION_JSON)
                .body("{\"code\":\"sh\",\"started\":true}"));
    assertThat(client.runNow("sh").path("started").asBoolean()).isTrue();
    server.reset();
    server
        .expect(requestTo(BASE + "/sources/sh/run"))
        .andRespond(
            withStatus(HttpStatus.CONFLICT)
                .contentType(MediaType.APPLICATION_JSON)
                .body("{\"error\":\"다른 수집이 돌고 있어요. 끝난 뒤 다시 해 주세요.\"}"));
    assertThatThrownBy(() -> client.runNow("sh"))
        .isInstanceOfSatisfying(
            CustomException.class,
            e -> {
              assertThat(e.errorCode()).isEqualTo(ErrorCode.CONFLICT);
              assertThat(e.getMessage()).startsWith("다른 수집이 돌고 있어요");
            });
  }
}
