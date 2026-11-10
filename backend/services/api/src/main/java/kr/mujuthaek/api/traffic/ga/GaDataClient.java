package kr.mujuthaek.api.traffic.ga;

import com.nimbusds.jose.JOSEException;
import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.JWSHeader;
import com.nimbusds.jose.crypto.RSASSASigner;
import com.nimbusds.jwt.JWTClaimsSet;
import com.nimbusds.jwt.SignedJWT;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.GeneralSecurityException;
import java.security.KeyFactory;
import java.security.PrivateKey;
import java.security.spec.PKCS8EncodedKeySpec;
import java.time.Clock;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Base64;
import java.util.Date;
import java.util.List;
import java.util.Map;
import kr.mujuthaek.api.traffic.TrafficProperties;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.MediaType;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.web.client.RestClient;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

/**
 * Google Analytics 4 Data API(v1beta) 클라이언트. 서비스 계정 키(JSON)로 서명한 JWT를 액세스 토큰으로 바꿔 보고서를 받아요(읽기 전용
 * 권한). 키 파일 내용은 로그·오류에 남기지 않아요. 보고서는 한 번에 5개까지 묶어 보내요(batchRunReports).
 */
@Component
public class GaDataClient {

  static final String API = "https://analyticsdata.googleapis.com/v1beta";
  static final String SCOPE = "https://www.googleapis.com/auth/analytics.readonly";
  private static final int BATCH = 5;
  private static final JsonMapper JSON = JsonMapper.builder().build();

  /** 보고서 하나: 측정기준·측정항목 이름, 정렬할 측정항목(내림차순, 비면 측정기준 오름차순), 행 수, 이벤트 이름 거르기. */
  public record ReportSpec(
      List<String> dimensions,
      List<String> metrics,
      String orderByMetric,
      int limit,
      List<String> eventNames,
      String pathPrefix) {}

  /** 보고서 한 줄: 측정기준 값들과 측정항목 값들(같은 순서). */
  public record Row(List<String> dimensions, List<Long> metrics) {}

  /** 키 파일에서 읽은 서비스 계정. */
  private record Account(String email, String keyId, PrivateKey key, String tokenUri) {}

  private final TrafficProperties.Ga props;
  private final RestClient http;
  private final Clock clock;
  private final String api;
  private Account account;
  private String token;
  private Instant tokenExpires = Instant.EPOCH;

  @Autowired
  public GaDataClient(TrafficProperties properties, Clock clock) {
    this(properties.ga(), defaultBuilder(properties.ga()), clock, API);
  }

  GaDataClient(TrafficProperties.Ga props, RestClient.Builder builder, Clock clock, String api) {
    this.props = props;
    this.http = builder.build();
    this.clock = clock;
    this.api = api;
  }

  public boolean configured() {
    return props.configured();
  }

  /** 보고서들을 받아요(순서대로). 기간은 오늘 포함 최근 days일(속성 시간대 기준). */
  public List<List<Row>> run(List<ReportSpec> specs, int days) {
    List<List<Row>> out = new ArrayList<>();
    for (int i = 0; i < specs.size(); i += BATCH) {
      List<ReportSpec> chunk = specs.subList(i, Math.min(specs.size(), i + BATCH));
      List<Map<String, Object>> requests = chunk.stream().map(s -> request(s, days)).toList();
      JsonNode body =
          http.post()
              .uri(api + "/properties/{id}:batchRunReports", props.propertyId())
              .header("Authorization", "Bearer " + accessToken())
              .contentType(MediaType.APPLICATION_JSON)
              .body(Map.of("requests", requests))
              .retrieve()
              .body(JsonNode.class);
      JsonNode reports = body == null ? null : body.path("reports");
      for (int j = 0; j < chunk.size(); j++) {
        out.add(rows(reports == null ? null : reports.get(j)));
      }
    }
    return out;
  }

  static Map<String, Object> request(ReportSpec spec, int days) {
    var request = new java.util.LinkedHashMap<String, Object>();
    request.put(
        "dateRanges", List.of(Map.of("startDate", (days - 1) + "daysAgo", "endDate", "today")));
    request.put("dimensions", spec.dimensions().stream().map(d -> Map.of("name", d)).toList());
    request.put("metrics", spec.metrics().stream().map(m -> Map.of("name", m)).toList());
    request.put(
        "orderBys",
        List.of(
            spec.orderByMetric() == null
                ? Map.of("dimension", Map.of("dimensionName", spec.dimensions().getFirst()))
                : Map.of("metric", Map.of("metricName", spec.orderByMetric()), "desc", true)));
    if (spec.limit() > 0) {
      request.put("limit", spec.limit());
    }
    if (spec.pathPrefix() != null) {
      request.put(
          "dimensionFilter",
          Map.of(
              "filter",
              Map.of(
                  "fieldName",
                  "pagePath",
                  "stringFilter",
                  Map.of("matchType", "BEGINS_WITH", "value", spec.pathPrefix()))));
    } else if (spec.eventNames() != null && !spec.eventNames().isEmpty()) {
      request.put(
          "dimensionFilter",
          Map.of(
              "filter",
              Map.of(
                  "fieldName", "eventName", "inListFilter", Map.of("values", spec.eventNames()))));
    }
    return request;
  }

  /**
   * 실시간 보고서(최근 30분까지, 표준 보고서와 달리 바로 반영). minutes가 있으면 최근 그 분만 봐요.
   *
   * @param dimensions 측정기준(없으면 합계 한 줄)
   */
  public List<Row> realtime(List<String> dimensions, List<String> metrics, Integer minutes) {
    var request = new java.util.LinkedHashMap<String, Object>();
    if (!dimensions.isEmpty()) {
      request.put("dimensions", dimensions.stream().map(d -> Map.of("name", d)).toList());
    }
    request.put("metrics", metrics.stream().map(m -> Map.of("name", m)).toList());
    if (minutes != null) {
      request.put(
          "minuteRanges", List.of(Map.of("startMinutesAgo", minutes - 1, "endMinutesAgo", 0)));
    }
    JsonNode body =
        http.post()
            .uri(api + "/properties/{id}:runRealtimeReport", props.propertyId())
            .header("Authorization", "Bearer " + accessToken())
            .contentType(MediaType.APPLICATION_JSON)
            .body(request)
            .retrieve()
            .body(JsonNode.class);
    return rows(body);
  }

  private static List<Row> rows(JsonNode report) {
    List<Row> out = new ArrayList<>();
    if (report == null) {
      return out;
    }
    for (JsonNode row : report.path("rows")) {
      List<String> dims = new ArrayList<>();
      row.path("dimensionValues").forEach(v -> dims.add(v.path("value").asString("")));
      List<Long> values = new ArrayList<>();
      row.path("metricValues")
          .forEach(
              v -> {
                try {
                  values.add(Math.round(Double.parseDouble(v.path("value").asString("0"))));
                } catch (NumberFormatException e) {
                  values.add(0L);
                }
              });
      out.add(new Row(dims, values));
    }
    return out;
  }

  /** 액세스 토큰. 만료 1분 전까지 다시 쓰고, 지나면 서명한 JWT로 새로 받아요. */
  synchronized String accessToken() {
    Instant now = clock.instant();
    if (token != null && now.isBefore(tokenExpires.minusSeconds(60))) {
      return token;
    }
    Account a = account();
    String assertion;
    try {
      var claims =
          new JWTClaimsSet.Builder()
              .issuer(a.email())
              .audience(a.tokenUri())
              .claim("scope", SCOPE)
              .issueTime(Date.from(now))
              .expirationTime(Date.from(now.plusSeconds(3600)))
              .build();
      var jwt =
          new SignedJWT(new JWSHeader.Builder(JWSAlgorithm.RS256).keyID(a.keyId()).build(), claims);
      jwt.sign(new RSASSASigner(a.key()));
      assertion = jwt.serialize();
    } catch (JOSEException e) {
      throw new IllegalStateException("GA 서비스 계정 서명에 실패했어요", e);
    }
    var form = new LinkedMultiValueMap<String, String>();
    form.add("grant_type", "urn:ietf:params:oauth:grant-type:jwt-bearer");
    form.add("assertion", assertion);
    JsonNode body =
        http.post()
            .uri(a.tokenUri())
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .body(form)
            .retrieve()
            .body(JsonNode.class);
    if (body == null || !body.path("access_token").isString()) {
      throw new IllegalStateException("GA 액세스 토큰을 받지 못했어요");
    }
    token = body.path("access_token").asString();
    tokenExpires = now.plusSeconds(body.path("expires_in").asLong(3600));
    return token;
  }

  private Account account() {
    if (account != null) {
      return account;
    }
    try {
      JsonNode key = JSON.readTree(Files.readString(Path.of(props.credentialsFile())));
      String pem =
          key.path("private_key")
              .asString("")
              .replace("-----BEGIN PRIVATE KEY-----", "")
              .replace("-----END PRIVATE KEY-----", "")
              .replaceAll("\\s", "");
      PrivateKey privateKey =
          KeyFactory.getInstance("RSA")
              .generatePrivate(new PKCS8EncodedKeySpec(Base64.getDecoder().decode(pem)));
      account =
          new Account(
              key.path("client_email").asString(),
              key.path("private_key_id").asString(null),
              privateKey,
              key.path("token_uri").asString("https://oauth2.googleapis.com/token"));
      return account;
    } catch (IOException | GeneralSecurityException | IllegalArgumentException e) {
      // 키 내용은 메시지에 넣지 않아요
      throw new IllegalStateException("GA 서비스 계정 키 파일을 읽지 못했어요: " + e.getClass().getSimpleName());
    }
  }

  private static RestClient.Builder defaultBuilder(TrafficProperties.Ga props) {
    var factory = new SimpleClientHttpRequestFactory();
    factory.setConnectTimeout(props.timeout());
    factory.setReadTimeout(props.timeout());
    return RestClient.builder().requestFactory(factory);
  }
}
