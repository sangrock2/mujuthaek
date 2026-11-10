package kr.mujuthaek.api.area.geocode;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.client.ExpectedCount.never;
import static org.springframework.test.web.client.ExpectedCount.once;
import static org.springframework.test.web.client.ExpectedCount.times;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.content;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.List;
import kr.mujuthaek.api.area.geocode.CoordOutcome.Failed;
import kr.mujuthaek.api.area.geocode.CoordOutcome.Found;
import kr.mujuthaek.api.area.geocode.CoordOutcome.NotFound;
import kr.mujuthaek.api.area.geocode.CoordOutcome.Rejected;
import kr.mujuthaek.api.area.geocode.SearchOutcome.Reason;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.web.client.RestClient;

/** 가짜 서버로 좌표제공 API 응답마다. 진짜 키 없이 돌아요. */
class JusoCoordClientTest {

  private static final String URL = "https://juso.test/addrlink/addrCoordApi.do";
  private static final String KEY = "test-key";
  // 검색 API가 준 금천구 시흥대로 377 (사전에 없는 새 건물)
  private static final JusoResult BUILDING =
      new JusoResult(
          "1154510200",
          "시흥대로",
          "0",
          "377",
          "0",
          "115453116001",
          null,
          "서울특별시",
          "금천구",
          "독산동",
          null,
          null);

  private final List<Long> sleeps = new ArrayList<>();
  private MockRestServiceServer server;

  private JusoCoordClient client(String key) {
    var builder = RestClient.builder();
    server = MockRestServiceServer.bindTo(builder).build();
    return new JusoCoordClient(
        new JusoCoordProperties(URL, key, 5, 10000, 2, Duration.ofSeconds(1)),
        builder,
        sleeps::add,
        Clock.fixed(Instant.parse("2026-10-25T01:00:00Z"), ZoneOffset.UTC));
  }

  @Test
  void returnsTheEntranceCoordinateAndSendsTheKeyInTheForm() {
    var client = client(KEY);
    var form = new LinkedMultiValueMap<String, String>();
    form.add("confmKey", KEY);
    form.add("admCd", "1154510200");
    form.add("rnMgtSn", "115453116001");
    form.add("udrtYn", "0");
    form.add("buldMnnm", "377");
    form.add("buldSlno", "0");
    form.add("resultType", "json");
    server
        .expect(once(), requestTo(URL))
        .andExpect(method(HttpMethod.POST))
        .andExpect(content().formData(form))
        .andRespond(
            withSuccess(
                """
                {"results":{"common":{"errorCode":"0","errorMessage":"정상","totalCount":"1"},
                 "juso":[{"admCd":"1154510200","entX":"948120.123","entY":"1941235.456","bdNm":"새건물"}]}}""",
                MediaType.APPLICATION_JSON));

    assertThat(client.coordinates(BUILDING)).isEqualTo(new Found(948120.123, 1941235.456));
    server.verify();
  }

  @Test
  void withoutAKeyItDoesNotCall() {
    var client = client(" ");
    server.expect(never(), requestTo(URL));

    assertThat(client.coordinates(BUILDING)).isEqualTo(new Failed(Reason.NO_KEY, null));
    server.verify();
  }

  @Test
  void keyErrorStopsAtOnce() {
    var client = client(KEY);
    server
        .expect(once(), requestTo(URL))
        .andRespond(withSuccess(error("E0001", "승인되지 않은 KEY 입니다."), MediaType.APPLICATION_JSON));

    assertThat(client.coordinates(BUILDING)).isEqualTo(new Failed(Reason.KEY_REJECTED, "E0001"));
    server.verify();
  }

  @Test
  void systemErrorIsRetriedThenUnavailable() {
    var client = client(KEY);
    server
        .expect(times(3), requestTo(URL))
        .andRespond(withSuccess(error("-999", "시스템 에러"), MediaType.APPLICATION_JSON));

    assertThat(client.coordinates(BUILDING)).isEqualTo(new Failed(Reason.UNAVAILABLE, "-999"));
    assertThat(sleeps).containsExactly(500L, 1000L);
    server.verify();
  }

  @Test
  void requestValueErrorIsNotRetried() {
    var client = client(KEY);
    server
        .expect(once(), requestTo(URL))
        .andRespond(withSuccess(error("E0005", "검색어가 입력되지 않았습니다."), MediaType.APPLICATION_JSON));

    assertThat(client.coordinates(BUILDING)).isEqualTo(new Rejected("E0005"));
    server.verify();
  }

  @Test
  void emptyOrBrokenCoordinatesAreNotFound() {
    var client = client(KEY);
    server
        .expect(once(), requestTo(URL))
        .andRespond(
            withSuccess(
                """
                {"results":{"common":{"errorCode":"0","totalCount":"0"},"juso":[]}}""",
                MediaType.APPLICATION_JSON));
    server
        .expect(once(), requestTo(URL))
        .andRespond(
            withSuccess(
                """
                {"results":{"common":{"errorCode":"0","totalCount":"1"},"juso":[{"entX":"","entY":null}]}}""",
                MediaType.APPLICATION_JSON));

    assertThat(client.coordinates(BUILDING)).isEqualTo(new NotFound());
    assertThat(client.coordinates(BUILDING)).isEqualTo(new NotFound());
    server.verify();
  }

  @Test
  void aSearchResultWithoutTheRoadCodeIsNotSent() {
    var client = client(KEY);
    server.expect(never(), requestTo(URL));
    var noRoadCode =
        new JusoResult(
            "1154510200", "시흥대로", "0", "377", "0", null, null, null, null, null, null, null);

    assertThat(client.coordinates(noRoadCode)).isEqualTo(new Rejected("MISSING_FIELDS"));
    server.verify();
  }

  private static String error(String code, String message) {
    return """
        {"results":{"common":{"errorCode":"%s","errorMessage":"%s","totalCount":"0"},"juso":null}}"""
        .formatted(code, message);
  }
}
