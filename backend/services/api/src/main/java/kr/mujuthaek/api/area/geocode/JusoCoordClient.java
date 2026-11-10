package kr.mujuthaek.api.area.geocode;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import java.time.Clock;
import java.util.List;
import java.util.Set;
import kr.mujuthaek.api.area.geocode.CoordOutcome.Failed;
import kr.mujuthaek.api.area.geocode.CoordOutcome.Found;
import kr.mujuthaek.api.area.geocode.CoordOutcome.NotFound;
import kr.mujuthaek.api.area.geocode.CoordOutcome.Rejected;
import kr.mujuthaek.api.area.geocode.JusoSearchClient.Sleeper;
import kr.mujuthaek.api.area.geocode.SearchOutcome.Reason;
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
 * 도로명주소 좌표제공 API 클라이언트. 사전에 아직 없는 새 건물(예: 금천구 시흥대로 377)의 출입구 좌표를 검색 결과 칸(법정동코드·도로명코드·지하 여부·건물번호)으로
 * 받아요. 좌표는 UTM-K(EPSG:5179)라 경위도로 바꾸는 건 부르는 쪽에서 해요.
 *
 * <p>검색 API 클라이언트({@link JusoSearchClient})와 같은 규칙이에요: 승인키는 POST 폼으로(URL·로그에 안 남게), 시스템
 * 오류(-999)·HTTP 5xx·연결 실패는 {@code retries}번 다시, 승인키 오류는 바로 {@link Reason#KEY_REJECTED}, 요청 값 문제는 바로
 * {@link Rejected}.
 */
@Component
public class JusoCoordClient implements AddressCoordinates {

  private static final Logger log = LoggerFactory.getLogger(JusoCoordClient.class);
  private static final Set<String> KEY_ERRORS = Set.of("E0001", "E0014");
  private static final String SYSTEM_ERROR = "-999";

  private final JusoCoordProperties properties;
  private final RestClient http;
  private final Sleeper sleeper;
  private final CallLimiter limiter;

  @Autowired
  public JusoCoordClient(JusoCoordProperties properties) {
    this(properties, defaultBuilder(properties), Sleeper.REAL, Clock.systemUTC());
  }

  JusoCoordClient(
      JusoCoordProperties properties, RestClient.Builder builder, Sleeper sleeper, Clock clock) {
    this.properties = properties;
    this.http = builder.baseUrl(properties.baseUrl()).build();
    this.sleeper = sleeper;
    this.limiter = new CallLimiter(properties.perSecond(), properties.perDay(), clock, sleeper);
  }

  @Override
  public CoordOutcome coordinates(JusoResult building) {
    if (!properties.hasKey()) {
      return new Failed(Reason.NO_KEY, null);
    }
    if (building.admCd() == null || building.rnMgtSn() == null || building.buldMnnm() == null) {
      return new Rejected("MISSING_FIELDS");
    }
    String last = null;
    for (int attempt = 0; attempt <= properties.retries(); attempt++) {
      if (attempt > 0) {
        sleeper.sleep(500L * attempt);
      }
      if (!limiter.acquire()) {
        log.warn("도로명주소 좌표제공 API 하루 호출 수({})를 넘었어요", properties.perDay());
        return new Failed(Reason.RATE_LIMITED, null);
      }
      try {
        Response body = call(building);
        Response.Common common =
            body == null || body.results() == null ? null : body.results().common();
        if (common == null) {
          last = "EMPTY_BODY";
          continue;
        }
        String code = common.errorCode();
        if ("0".equals(code)) {
          return first(body.results().juso());
        }
        if (KEY_ERRORS.contains(code)) {
          log.warn("도로명주소 좌표제공 API 승인키 오류: {}", code);
          return new Failed(Reason.KEY_REJECTED, code);
        }
        if (!SYSTEM_ERROR.equals(code)) {
          return new Rejected(code);
        }
        last = code;
      } catch (RestClientResponseException e) {
        if (e.getStatusCode().is4xxClientError()) {
          log.warn("도로명주소 좌표제공 API HTTP {}", e.getStatusCode().value());
          return new Failed(Reason.UNAVAILABLE, "HTTP_" + e.getStatusCode().value());
        }
        last = "HTTP_" + e.getStatusCode().value();
      } catch (RestClientException e) {
        // 메시지에 요청 정보가 들어갈 수 있어서 종류만 남겨요
        last = e.getClass().getSimpleName();
      }
    }
    log.warn("도로명주소 좌표제공 API를 쓸 수 없어요 ({}번 시도, 마지막 {})", properties.retries() + 1, last);
    return new Failed(Reason.UNAVAILABLE, last);
  }

  /** 첫 줄의 좌표. 칸이 비었거나 숫자가 아니면 없음으로 봐요. */
  private static CoordOutcome first(List<Response.Coord> juso) {
    if (juso == null || juso.isEmpty()) {
      return new NotFound();
    }
    try {
      Response.Coord c = juso.getFirst();
      return new Found(Double.parseDouble(c.entX().trim()), Double.parseDouble(c.entY().trim()));
    } catch (NullPointerException | NumberFormatException e) {
      return new NotFound();
    }
  }

  private Response call(JusoResult b) {
    var form = new LinkedMultiValueMap<String, String>();
    form.add("confmKey", properties.apiKey());
    form.add("admCd", b.admCd());
    form.add("rnMgtSn", b.rnMgtSn());
    form.add("udrtYn", b.underground() ? "1" : "0");
    form.add("buldMnnm", String.valueOf(b.buildingMain()));
    form.add("buldSlno", String.valueOf(b.buildingSub()));
    form.add("resultType", "json");
    return http.post()
        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
        .accept(MediaType.APPLICATION_JSON)
        .body(form)
        .retrieve()
        .body(Response.class);
  }

  private static RestClient.Builder defaultBuilder(JusoCoordProperties properties) {
    var factory = new SimpleClientHttpRequestFactory();
    factory.setConnectTimeout(properties.timeout());
    factory.setReadTimeout(properties.timeout());
    return RestClient.builder().requestFactory(factory);
  }

  @JsonIgnoreProperties(ignoreUnknown = true)
  record Response(Results results) {

    @JsonIgnoreProperties(ignoreUnknown = true)
    record Results(Common common, List<Coord> juso) {}

    @JsonIgnoreProperties(ignoreUnknown = true)
    record Common(String errorCode, String errorMessage, String totalCount) {}

    /** 좌표 한 줄. entX·entY는 UTM-K(미터)로 문자열이에요. */
    @JsonIgnoreProperties(ignoreUnknown = true)
    record Coord(String entX, String entY, String bdNm) {}
  }
}
