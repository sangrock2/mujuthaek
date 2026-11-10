package kr.mujuthaek.api.notice.client;

import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.function.Supplier;
import kr.mujuthaek.api.common.exception.CustomException;
import kr.mujuthaek.api.common.exception.ErrorCode;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.client.BufferingClientHttpRequestFactory;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestClientResponseException;
import tools.jackson.databind.JsonNode;

/**
 * 추출 서비스 검수 API 클라이언트. 목록·상세는 받은 JSON 그대로, 승인·반려는 메모만 보내요(고친 결과를 보내는 칸별 수정은 아직 없어요).
 *
 * <p>오류: 404는 {@link ErrorCode#NOTICE_REVIEW_NOT_FOUND}, 409(이미 처리됨·새 버전으로 대체됨)는 {@link
 * ErrorCode#NOTICE_REVIEW_CONFLICT}, 422(형식이 맞지 않음)는 {@link ErrorCode#NOTICE_REVIEW_INVALID}로 바꾸고
 * 검수 API의 설명(error)을 그대로 detail에 넣어요. 연결 실패·인증 실패·5xx는 {@link
 * ErrorCode#NOTICE_REVIEW_UNAVAILABLE}이고 토큰·주소는 로그에 남기지 않아요.
 */
@Component
public class ExtractionReviewClient {

  private static final Logger log = LoggerFactory.getLogger(ExtractionReviewClient.class);

  /** 목록 한 번에 받는 최대 건수(검수 API 상한과 같음). */
  private static final int LIST_LIMIT = 1000;

  private final RestClient http;

  @Autowired
  public ExtractionReviewClient(ExtractionReviewProperties properties) {
    this(properties, defaultBuilder(properties));
  }

  /** 요청 빌더를 받아요(시험에서 가짜 서버를 붙일 때). */
  public ExtractionReviewClient(ExtractionReviewProperties properties, RestClient.Builder builder) {
    builder.baseUrl(properties.baseUrl());
    if (properties.hasToken()) {
      builder.defaultHeader(HttpHeaders.AUTHORIZATION, "Bearer " + properties.token());
    }
    this.http = builder.build();
  }

  /** 그 상태(PENDING·APPROVED·REJECTED·SUPERSEDED)의 검수 목록. 응답의 items 배열(오래된 것부터 최대 1000건). */
  public JsonNode list(String status) {
    JsonNode body = listBody("/reviews", status);
    return body == null ? null : body.get("items");
  }

  /**
   * 대기 중인 공고 검수의 건수와 가장 오래된 한 건만 {items(0~1건), total}. 숫자·남은 건수만 필요할 때 목록 전체(최대 1000건)를 받지 않게
   * 해요(2026-10-29 부하 시험: 전체 목록 조회가 DB를 가장 많이 썼어요). total은 추출 서비스가 따로 세요.
   */
  public JsonNode pendingHead() {
    return head("/reviews");
  }

  /** 대기 중인 혜택 검수의 건수와 가장 오래된 한 건만 {items(0~1건), total}. */
  public JsonNode benefitPendingHead() {
    return head("/benefit-reviews");
  }

  private JsonNode head(String path) {
    return call(
        () ->
            http.get()
                .uri(path + "?status={s}&limit=1", "PENDING")
                .retrieve()
                .body(JsonNode.class));
  }

  /**
   * 대기 중인 공고 검수 한 페이지 {items, total, hasMore} (관리자 검수 무한 스크롤). reason(MUST·CHECK·FORMAT)이 null이면
   * 전부, after가 null이면 처음부터예요.
   */
  public JsonNode reviewPage(String reason, After after, int limit) {
    Map<String, Object> query = new LinkedHashMap<>();
    query.put("reason", reason);
    return pendingPage("/reviews", query, after, limit);
  }

  /** 대기 중인 혜택 검수 한 페이지 {items, total, hasMore}. reported가 null이면 전부(true면 정책 제보로 다시 연 건만). */
  public JsonNode benefitReviewPage(Boolean reported, After after, int limit) {
    Map<String, Object> query = new LinkedHashMap<>();
    query.put("reported", reported);
    return pendingPage("/benefit-reviews", query, after, limit);
  }

  /** 이어 받을 위치: 앞 페이지 마지막 건의 들어온 시각과 ID. 시각은 UTC(Z)로 보내요(+09:00의 「+」가 주소에서 띄어쓰기로 읽히지 않게). */
  public record After(Instant at, String id) {}

  private JsonNode pendingPage(String path, Map<String, Object> filters, After after, int limit) {
    Map<String, Object> vars = new LinkedHashMap<>();
    StringBuilder uri = new StringBuilder(path).append("?status=PENDING&limit={limit}");
    vars.put("limit", limit);
    filters.forEach(
        (key, value) -> {
          if (value != null) {
            uri.append('&').append(key).append("={").append(key).append('}');
            vars.put(key, value);
          }
        });
    if (after != null) {
      uri.append("&afterAt={afterAt}&afterId={afterId}");
      vars.put("afterAt", after.at().toString());
      vars.put("afterId", after.id());
    }
    return call(() -> http.get().uri(uri.toString(), vars).retrieve().body(JsonNode.class));
  }

  private JsonNode listBody(String path, String status) {
    return call(
        () ->
            http.get()
                .uri(path + "?status={s}&limit={n}", status, LIST_LIMIT)
                .retrieve()
                .body(JsonNode.class));
  }

  /** 목록 응답의 전체 건수(total이 없는 옛 응답이면 items 길이). */
  public static int total(JsonNode body) {
    if (body == null) {
      return 0;
    }
    JsonNode total = body.get("total");
    if (total != null && total.isNumber()) {
      return total.asInt();
    }
    JsonNode items = body.get("items");
    return items == null ? 0 : items.size();
  }

  /** 검수 상세(후보·이슈·받은 이벤트 포함). */
  public JsonNode detail(String jobId) {
    return call(() -> http.get().uri("/reviews/{id}", jobId).retrieve().body(JsonNode.class));
  }

  /** 처리 통계(최근 days일·오늘). */
  /** 처리 기록 (추출 GET /reviews/activity): 공고·혜택 검수 승인·반려·다시 열기, 최근 순. */
  public JsonNode activity(int days) {
    return call(
        () ->
            http.get()
                .uri("/reviews/activity?days={d}&limit=300", days)
                .retrieve()
                .body(JsonNode.class));
  }

  public JsonNode stats(int days) {
    return call(
        () -> http.get().uri("/reviews/stats?days={d}", days).retrieve().body(JsonNode.class));
  }

  /**
   * 승인. 검수 API가 그 작업의 결과를 다시 발행해요.
   *
   * @param edits 칸별 수정 [{path, value}]. 비면 그대로 승인
   * @param reviewer 처리 기록에 남길 검수자(로그인 계정 ID)
   */
  public JsonNode approve(
      String jobId, String note, String reviewer, List<Map<String, Object>> edits) {
    Map<String, Object> body = body(note, reviewer);
    if (edits != null && !edits.isEmpty()) {
      body.put("edits", edits);
    }
    return post(jobId, "approve", body);
  }

  /**
   * 이미 발행한 결과를 검수 대기로 다시 열어요(사용자 제보로 공고 값을 고칠 때). 응답: {jobId, reviewStatus, reopened}.
   *
   * @param rawPostId 공고의 지금 원본 글 ID
   */
  public JsonNode reopen(String rawPostId, String reviewer, String note) {
    Map<String, Object> body = body(note, reviewer);
    body.put("rawPostId", rawPostId);
    return call(
        () ->
            http.post()
                .uri("/reviews/reopen")
                .contentType(MediaType.APPLICATION_JSON)
                .body(body)
                .retrieve()
                .body(JsonNode.class));
  }

  /** 반려. 발행하지 않아요. */
  public JsonNode reject(String jobId, String note, String reviewer) {
    return post(jobId, "reject", body(note, reviewer));
  }

  /** 혜택 검수 상세: payload(정제 결과)·source(받은 원본). */
  public JsonNode benefitDetail(String reviewId) {
    return call(
        () -> http.get().uri("/benefit-reviews/{id}", reviewId).retrieve().body(JsonNode.class));
  }

  /**
   * 혜택 검수 승인(approve)·반려(reject). 검수 API가 고친 결과를 다시 발행해요(반려는 relevant=false).
   *
   * @param edits 칸별 수정 [{path, value}]. 승인에서만 보내요
   */
  public JsonNode benefitDecide(
      String reviewId,
      String action,
      String note,
      String reviewer,
      List<Map<String, Object>> edits) {
    Map<String, Object> body = body(note, reviewer);
    if (edits != null && !edits.isEmpty()) {
      body.put("edits", edits);
    }
    return call(
        () ->
            http.post()
                .uri("/benefit-reviews/{id}/{action}", reviewId, action)
                .contentType(MediaType.APPLICATION_JSON)
                .body(body)
                .retrieve()
                .body(JsonNode.class));
  }

  /** 정책 제보로 그 정책의 가장 새 정제 결과를 검수 대기로 다시 열어요. 응답: {reviewId, reopened}. */
  public JsonNode benefitReopen(String rawPolicyId, String reviewer, String note) {
    Map<String, Object> body = body(note, reviewer);
    body.put("rawPolicyId", rawPolicyId);
    return call(
        () ->
            http.post()
                .uri("/benefit-reviews/reopen")
                .contentType(MediaType.APPLICATION_JSON)
                .body(body)
                .retrieve()
                .body(JsonNode.class));
  }

  /** 그 정책의 가장 새 정제 결과 요약(제목·출처·relevant). 없으면 {@link ErrorCode#NOTICE_REVIEW_NOT_FOUND}. */
  public JsonNode benefit(String rawPolicyId) {
    return call(
        () -> http.get().uri("/benefits/{id}", rawPolicyId).retrieve().body(JsonNode.class));
  }

  private static Map<String, Object> body(String note, String reviewer) {
    Map<String, Object> body = new LinkedHashMap<>();
    if (note != null) {
      body.put("note", note);
    }
    if (reviewer != null) {
      body.put("reviewer", reviewer);
    }
    return body;
  }

  private JsonNode post(String jobId, String action, Map<String, Object> body) {
    return call(
        () ->
            http.post()
                .uri("/reviews/{id}/{action}", jobId, action)
                .contentType(MediaType.APPLICATION_JSON)
                .body(body)
                .retrieve()
                .body(JsonNode.class));
  }

  private JsonNode call(Supplier<JsonNode> request) {
    try {
      return request.get();
    } catch (RestClientResponseException e) {
      int status = e.getStatusCode().value();
      String detail = upstreamError(e);
      switch (status) {
        case 404 -> throw new CustomException(ErrorCode.NOTICE_REVIEW_NOT_FOUND, detail);
        case 409 -> throw new CustomException(ErrorCode.NOTICE_REVIEW_CONFLICT, detail);
        case 400, 422 -> throw new CustomException(ErrorCode.NOTICE_REVIEW_INVALID, detail);
        default -> {
          log.warn("검수 API가 오류로 답했어요 (status {})", status);
          throw new CustomException(ErrorCode.NOTICE_REVIEW_UNAVAILABLE);
        }
      }
    } catch (RestClientException e) {
      log.warn("검수 API에 연결하지 못했어요 ({})", e.getClass().getSimpleName());
      throw new CustomException(ErrorCode.NOTICE_REVIEW_UNAVAILABLE);
    }
  }

  /** 검수 API 오류 본문의 error(한국어 설명). 없으면 null(공통 문구를 써요). */
  private static String upstreamError(RestClientResponseException e) {
    try {
      JsonNode body = e.getResponseBodyAs(JsonNode.class);
      JsonNode error = body == null ? null : body.get("error");
      return error != null && error.isString() ? error.asString() : null;
    } catch (RuntimeException ignored) {
      return null;
    }
  }

  private static RestClient.Builder defaultBuilder(ExtractionReviewProperties properties) {
    var factory = new SimpleClientHttpRequestFactory();
    factory.setConnectTimeout(properties.timeout());
    factory.setReadTimeout(properties.timeout());
    // 본문을 모아 Content-Length를 붙여 보내요. 조각 전송(chunked)이면 파이썬 http.server가 본문을 빈 것으로 읽어 승인·반려·다시 열기가
    // 400이 됐어요(2026-10-25 로컬 실제 흐름에서 발견, 가짜 서버 시험으로는 안 보임)
    return RestClient.builder().requestFactory(new BufferingClientHttpRequestFactory(factory));
  }
}
