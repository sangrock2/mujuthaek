package kr.mujuthaek.api.traffic.ga;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.content;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.header;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyPairGenerator;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Base64;
import java.util.List;
import kr.mujuthaek.api.traffic.TrafficProperties;
import kr.mujuthaek.api.traffic.ga.GaDataClient.ReportSpec;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;

/** GA Data API: 서비스 계정 키로 토큰을 받고, 보고서를 5개씩 묶어 묻고, 토큰은 다시 써요. 가짜 서버만 써요(Google 호출 없음). */
class GaDataClientTest {

  @TempDir Path dir;

  @Test
  void 토큰을_받아_보고서를_묶어_묻고_줄로_바꾼다() throws Exception {
    var pair = KeyPairGenerator.getInstance("RSA");
    pair.initialize(2048);
    String pem =
        "-----BEGIN PRIVATE KEY-----\n"
            + Base64.getMimeEncoder()
                .encodeToString(pair.generateKeyPair().getPrivate().getEncoded())
                .replace("\r\n", "\n")
            + "\n-----END PRIVATE KEY-----\n";
    Path key = dir.resolve("key.json");
    // 실제 키 파일처럼 private_key 안의 줄바꿈은 JSON 이스케이프(\n)로 들어가요
    var json = tools.jackson.databind.json.JsonMapper.builder().build().createObjectNode();
    json.put("client_email", "admin-dashboard@test.iam.gserviceaccount.com");
    json.put("private_key_id", "k1");
    json.put("private_key", pem);
    json.put("token_uri", "http://token.test/token");
    Files.writeString(key, json.toString());
    var props =
        new TrafficProperties.Ga("123", key.toString(), Duration.ofHours(1), Duration.ofSeconds(5));
    RestClient.Builder builder = RestClient.builder();
    MockRestServiceServer server = MockRestServiceServer.bindTo(builder).build();
    var client =
        new GaDataClient(
            props,
            builder,
            Clock.fixed(Instant.parse("2026-10-26T03:00:00Z"), ZoneOffset.UTC),
            "http://ga.test");

    server
        .expect(requestTo("http://token.test/token"))
        .andExpect(method(HttpMethod.POST))
        .andExpect(content().string(org.hamcrest.Matchers.containsString("grant_type=urn%3Aietf")))
        .andRespond(
            withSuccess(
                "{\"access_token\":\"t1\",\"expires_in\":3600}", MediaType.APPLICATION_JSON));
    server
        .expect(requestTo("http://ga.test/properties/123:batchRunReports"))
        .andExpect(header("Authorization", "Bearer t1"))
        .andExpect(
            content().string(org.hamcrest.Matchers.containsString("\"startDate\":\"6daysAgo\"")))
        .andRespond(
            withSuccess(
                "{\"reports\":[{\"rows\":[{\"dimensionValues\":[{\"value\":\"20261026\"}],"
                    + "\"metricValues\":[{\"value\":\"12\"},{\"value\":\"3.0\"}]}]},{},{},{},{}]}",
                MediaType.APPLICATION_JSON));
    server
        .expect(requestTo("http://ga.test/properties/123:batchRunReports"))
        .andExpect(header("Authorization", "Bearer t1")) // 토큰을 다시 받지 않아요
        .andRespond(withSuccess("{\"reports\":[{}]}", MediaType.APPLICATION_JSON));

    var spec =
        new ReportSpec(List.of("date"), List.of("activeUsers", "sessions"), null, 0, null, null);
    var rows = client.run(List.of(spec, spec, spec, spec, spec, spec), 7);

    server.verify();
    assertThat(rows).hasSize(6);
    assertThat(rows.getFirst())
        .singleElement()
        .satisfies(
            r -> {
              assertThat(r.dimensions()).containsExactly("20261026");
              assertThat(r.metrics()).containsExactly(12L, 3L);
            });
    assertThat(rows.get(5)).isEmpty();
  }

  @Test
  void 이벤트_이름으로_거르고_측정항목으로_정렬한다() {
    var request =
        GaDataClient.request(
            new ReportSpec(
                List.of("eventName"),
                List.of("eventCount"),
                "eventCount",
                0,
                List.of("judgment_run"),
                null),
            28);
    assertThat(request.toString()).contains("27daysAgo", "judgment_run", "desc=true");
  }
}
