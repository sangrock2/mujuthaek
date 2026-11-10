package kr.mujuthaek.api.area.geocode;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.client.ExpectedCount.once;
import static org.springframework.test.web.client.ExpectedCount.times;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.content;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withServerError;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withStatus;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.List;
import kr.mujuthaek.api.area.geocode.SearchOutcome.Failed;
import kr.mujuthaek.api.area.geocode.SearchOutcome.Found;
import kr.mujuthaek.api.area.geocode.SearchOutcome.NotFound;
import kr.mujuthaek.api.area.geocode.SearchOutcome.Reason;
import kr.mujuthaek.api.area.geocode.SearchOutcome.Rejected;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.web.client.RestClient;

/** 가짜 서버로 검색 API 응답마다. 진짜 키 없이 돌아요. */
class JusoSearchClientTest {

  private static final String URL = "https://juso.test/addrlink/addrLinkApi.do";
  private static final String KEY = "test-key";

  private final List<Long> sleeps = new ArrayList<>();
  private MockRestServiceServer server;

  private JusoSearchClient client(String key) {
    return client(key, 10000);
  }

  private JusoSearchClient client(String key, int perDay) {
    var builder = RestClient.builder();
    server = MockRestServiceServer.bindTo(builder).build();
    return new JusoSearchClient(
        new JusoSearchProperties(URL, key, 5, perDay, 2, Duration.ofSeconds(1)),
        builder,
        sleeps::add,
        Clock.fixed(Instant.parse("2026-10-23T01:00:00Z"), ZoneOffset.UTC));
  }

  @Test
  void dailyLimitStopsCallsAndCountsRetries() {
    var client = client(KEY, 2);
    server
        .expect(times(2), requestTo(URL))
        .andRespond(withSuccess(error("-999", "시스템 에러"), MediaType.APPLICATION_JSON));

    // 첫 시도 + 재시도 1번으로 하루 한도 2를 다 써서 세 번째는 부르지 않아요
    assertThat(client.search("초량상로 1-2")).isEqualTo(new Failed(Reason.RATE_LIMITED, null));
    assertThat(client.search("초량상로 1-2")).isEqualTo(new Failed(Reason.RATE_LIMITED, null));
    server.verify();
  }

  @Test
  void oneResultIsFoundAndKeyGoesInFormNotUrl() {
    var client = client(KEY);
    var form = new LinkedMultiValueMap<String, String>();
    form.add("confmKey", KEY);
    form.add("keyword", "부산광역시 중구 초량상로 1-2");
    form.add("currentPage", "1");
    form.add("countPerPage", "10");
    form.add("resultType", "json");
    server
        .expect(once(), requestTo(URL))
        .andExpect(method(HttpMethod.POST))
        .andExpect(content().formData(form))
        .andRespond(
            withSuccess(
                body("0", "1", juso("2611010100", "초량상로", "0", "1", "2")),
                MediaType.APPLICATION_JSON));

    SearchOutcome outcome = client.search("부산광역시 중구 초량상로 1-2");

    server.verify();
    assertThat(outcome).isInstanceOf(Found.class);
    JusoResult r = ((Found) outcome).results().getFirst();
    assertThat(r.sigunguCode()).isEqualTo("26110");
    assertThat(r.rn()).isEqualTo("초량상로");
    assertThat(r.underground()).isFalse();
    assertThat(r.buildingMain()).isEqualTo(1);
    assertThat(r.buildingSub()).isEqualTo(2);
    assertThat(r.jibunAddr()).isEqualTo("지번 주소");
  }

  @Test
  void manyResultsAreAllReturned() {
    var client = client(KEY);
    server
        .expect(requestTo(URL))
        .andRespond(
            withSuccess(
                body(
                    "0",
                    "2",
                    juso("1168010100", "테헤란로", "0", "152", "0")
                        + ","
                        + juso("4113510900", "판교역로", "1", "160", "0")),
                MediaType.APPLICATION_JSON));

    SearchOutcome outcome = client.search("역로");

    assertThat(((Found) outcome).results()).hasSize(2);
    assertThat(((Found) outcome).totalCount()).isEqualTo(2);
    assertThat(((Found) outcome).results().get(1).underground()).isTrue();
  }

  @Test
  void noResultsIsNotFound() {
    var client = client(KEY);
    server
        .expect(requestTo(URL))
        .andRespond(withSuccess(body("0", "0", ""), MediaType.APPLICATION_JSON));

    assertThat(client.search("없는 주소 999")).isInstanceOf(NotFound.class);
  }

  @Test
  void keywordProblemIsRejectedWithoutRetry() {
    var client = client(KEY);
    server
        .expect(once(), requestTo(URL))
        .andRespond(
            withSuccess(error("E0006", "주소를 상세히 입력해 주시기 바랍니다."), MediaType.APPLICATION_JSON));

    assertThat(client.search("서울")).isEqualTo(new Rejected("E0006"));
    server.verify();
    assertThat(sleeps).isEmpty();
  }

  @Test
  void badKeyFailsWithoutRetry() {
    var client = client(KEY);
    server
        .expect(once(), requestTo(URL))
        .andRespond(withSuccess(error("E0001", "승인되지 않은 KEY 입니다."), MediaType.APPLICATION_JSON));

    assertThat(client.search("초량상로 1-2")).isEqualTo(new Failed(Reason.KEY_REJECTED, "E0001"));
    server.verify();
  }

  @Test
  void systemErrorIsRetriedTwiceThenUnavailable() {
    var client = client(KEY);
    server
        .expect(times(3), requestTo(URL))
        .andRespond(withSuccess(error("-999", "시스템 에러"), MediaType.APPLICATION_JSON));

    assertThat(client.search("초량상로 1-2")).isEqualTo(new Failed(Reason.UNAVAILABLE, "-999"));
    server.verify();
    assertThat(sleeps).containsExactly(500L, 1000L);
  }

  @Test
  void serverErrorThenSuccessIsFound() {
    var client = client(KEY);
    server.expect(requestTo(URL)).andRespond(withServerError());
    server
        .expect(requestTo(URL))
        .andRespond(
            withSuccess(
                body("0", "1", juso("2611010100", "초량상로", "0", "1", "2")),
                MediaType.APPLICATION_JSON));

    assertThat(client.search("초량상로 1-2")).isInstanceOf(Found.class);
    server.verify();
  }

  @Test
  void clientHttpErrorFailsWithoutRetry() {
    var client = client(KEY);
    server.expect(once(), requestTo(URL)).andRespond(withStatus(HttpStatus.FORBIDDEN));

    assertThat(client.search("초량상로 1-2")).isEqualTo(new Failed(Reason.UNAVAILABLE, "HTTP_403"));
    server.verify();
  }

  @Test
  void keywordIsCleanedAndEmptyKeywordIsNotSent() {
    var client = client(KEY);
    server
        .expect(once(), requestTo(URL))
        .andExpect(
            content()
                .string(
                    org.hamcrest.Matchers.containsString(
                        "keyword=%EC%B4%88%EB%9F%89%EC%83%81%EB%A1%9C+1-2&")))
        .andRespond(withSuccess(body("0", "0", ""), MediaType.APPLICATION_JSON));

    assertThat(client.search("초량상로 <1-2>")).isInstanceOf(NotFound.class);
    assertThat(client.search(" %= ")).isEqualTo(new Rejected("E0005"));
    server.verify();
  }

  @Test
  void withoutKeyNothingIsCalled() {
    var client = client("");

    assertThat(client.search("초량상로 1-2")).isEqualTo(new Failed(Reason.NO_KEY, null));
    server.verify();
  }

  private static String body(String code, String total, String jusoItems) {
    return "{\"results\":{\"common\":{\"errorMessage\":\"정상\",\"countPerPage\":\"10\",\"totalCount\":\""
        + total
        + "\",\"errorCode\":\""
        + code
        + "\",\"currentPage\":\"1\"},\"juso\":["
        + jusoItems
        + "]}}";
  }

  private static String error(String code, String message) {
    return "{\"results\":{\"common\":{\"errorMessage\":\""
        + message
        + "\",\"countPerPage\":\"10\",\"totalCount\":\"0\",\"errorCode\":\""
        + code
        + "\",\"currentPage\":\"1\"},\"juso\":null}}";
  }

  static String juso(String admCd, String rn, String udrtYn, String main, String sub) {
    return "{\"roadAddr\":\"도로명 주소\",\"jibunAddr\":\"지번 주소\",\"zipNo\":\"48822\",\"admCd\":\""
        + admCd
        + "\",\"rnMgtSn\":\""
        + admCd.substring(0, 5)
        + "3000001\",\"bdMgtSn\":\"b\",\"siNm\":\"시\",\"sggNm\":\"구\",\"emdNm\":\"동\",\"rn\":\""
        + rn
        + "\",\"udrtYn\":\""
        + udrtYn
        + "\",\"buldMnnm\":\""
        + main
        + "\",\"buldSlno\":\""
        + sub
        + "\",\"mtYn\":\"0\",\"lnbrMnnm\":\"1\",\"lnbrSlno\":\"0\"}";
  }
}
