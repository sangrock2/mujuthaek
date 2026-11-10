package kr.mujuthaek.api.area.geocode;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import java.time.Clock;
import java.util.List;
import java.util.Set;
import kr.mujuthaek.api.area.geocode.SearchOutcome.Failed;
import kr.mujuthaek.api.area.geocode.SearchOutcome.Found;
import kr.mujuthaek.api.area.geocode.SearchOutcome.NotFound;
import kr.mujuthaek.api.area.geocode.SearchOutcome.Reason;
import kr.mujuthaek.api.area.geocode.SearchOutcome.Rejected;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.MediaType;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestClientResponseException;

/**
 * 도로명주소 검색 API 클라이언트. 주소 사전에서 못 찾은 주소(지번 주소, 건물명이 붙은 주소 등)를 검색해서 법정동코드·도로명·건물번호를 받아요.
 *
 * <p>승인키는 URL에 넣지 않으려고 POST 폼으로 보내요(오류 메시지·로그에 URL이 찍혀도 키가 안 나가게). 로그에는 오류 코드만 남겨요.
 *
 * <p>오류 처리: 시스템 오류(-999)·HTTP 5xx·연결 실패는 {@code retries}번 다시 부르고, 그래도 안 되면 {@link
 * Reason#UNAVAILABLE}. 승인키 오류는 바로 {@link Reason#KEY_REJECTED}. 검색어 문제는 다시 불러도 같아서 바로 {@link
 * Rejected}.
 */
@Component
public class JusoSearchClient implements AddressSearch {

  private static final Logger log = LoggerFactory.getLogger(JusoSearchClient.class);
  private static final Set<String> KEY_ERRORS = Set.of("E0001", "E0014");
  private static final String SYSTEM_ERROR = "-999";

  private final JusoSearchProperties properties;
  private final RestClient http;
  private final Sleeper sleeper;
  private final CallLimiter limiter;

  @Autowired
  public JusoSearchClient(JusoSearchProperties properties) {
    this(properties, defaultBuilder(properties), Sleeper.REAL, Clock.systemUTC());
  }

  JusoSearchClient(
      JusoSearchProperties properties, RestClient.Builder builder, Sleeper sleeper, Clock clock) {
    this.properties = properties;
    this.http = builder.baseUrl(properties.baseUrl()).build();
    this.sleeper = sleeper;
    this.limiter = new CallLimiter(properties.perSecond(), properties.perDay(), clock, sleeper);
  }

  /**
   * 검색어로 첫 쪽(최대 10개)을 받아요. 검색어는 주소 정리 결과를 넘기고, 여기서 API가 받지 않는 글자를 걸러요({@link JusoKeyword}). 거르고 나서
   * 비면 부르지 않고 E0005(검색어 없음)예요.
   */
  @Override
  public SearchOutcome search(String keyword) {
    if (!properties.hasKey()) {
      return new Failed(Reason.NO_KEY, null);
    }
    String cleaned = JusoKeyword.clean(keyword);
    if (cleaned.isEmpty()) {
      return new Rejected("E0005");
    }
    String last = null;
    for (int attempt = 0; attempt <= properties.retries(); attempt++) {
      if (attempt > 0) {
        sleeper.sleep(500L * attempt);
      }
      if (!limiter.acquire()) {
        log.warn("도로명주소 검색 API 하루 호출 수({})를 넘었어요", properties.perDay());
        return new Failed(Reason.RATE_LIMITED, null);
      }
      try {
        Response body = call(cleaned);
        Response.Common common =
            body == null || body.results() == null ? null : body.results().common();
        if (common == null) {
          last = "EMPTY_BODY";
          continue;
        }
        String code = common.errorCode();
        if ("0".equals(code)) {
          List<JusoResult> juso = body.results().juso() == null ? List.of() : body.results().juso();
          return juso.isEmpty() ? new NotFound() : new Found(juso, parseInt(common.totalCount()));
        }
        if (KEY_ERRORS.contains(code)) {
          log.warn("도로명주소 검색 API 승인키 오류: {}", code);
          return new Failed(Reason.KEY_REJECTED, code);
        }
        if (!SYSTEM_ERROR.equals(code)) {
          return new Rejected(code);
        }
        last = code;
      } catch (RestClientResponseException e) {
        if (e.getStatusCode().is4xxClientError()) {
          log.warn("도로명주소 검색 API HTTP {}", e.getStatusCode().value());
          return new Failed(Reason.UNAVAILABLE, "HTTP_" + e.getStatusCode().value());
        }
        last = "HTTP_" + e.getStatusCode().value();
      } catch (RestClientException e) {
        // 메시지에 요청 정보가 들어갈 수 있어서 종류만 남겨요
        last = e.getClass().getSimpleName();
      }
    }
    log.warn("도로명주소 검색 API를 쓸 수 없어요 ({}번 시도, 마지막 {})", properties.retries() + 1, last);
    return new Failed(Reason.UNAVAILABLE, last);
  }

  private Response call(String keyword) {
    var form = new LinkedMultiValueMap<String, String>();
    form.add("confmKey", properties.apiKey());
    form.add("keyword", keyword);
    form.add("currentPage", "1");
    form.add("countPerPage", "10");
    form.add("resultType", "json");
    return http.post()
        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
        .accept(MediaType.APPLICATION_JSON)
        .body(form)
        .retrieve()
        .body(Response.class);
  }

  private static RestClient.Builder defaultBuilder(JusoSearchProperties properties) {
    var factory = new SimpleClientHttpRequestFactory();
    factory.setConnectTimeout(properties.timeout());
    factory.setReadTimeout(properties.timeout());
    return RestClient.builder().requestFactory(factory);
  }

  private static int parseInt(String v) {
    try {
      return v == null ? 0 : Integer.parseInt(v.trim());
    } catch (NumberFormatException e) {
      return 0;
    }
  }

  /** 재시도 사이 기다리기. 테스트에서는 기다리지 않게 바꿔요. */
  interface Sleeper {
    Sleeper REAL =
        millis -> {
          try {
            Thread.sleep(millis);
          } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
          }
        };

    void sleep(long millis);
  }

  @JsonIgnoreProperties(ignoreUnknown = true)
  record Response(Results results) {

    @JsonIgnoreProperties(ignoreUnknown = true)
    record Results(Common common, List<JusoResult> juso) {}

    @JsonIgnoreProperties(ignoreUnknown = true)
    record Common(String errorCode, String errorMessage, String totalCount) {}
  }
}
