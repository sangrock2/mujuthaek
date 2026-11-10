package kr.mujuthaek.api.notice.service.internal;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.hamcrest.Matchers.startsWith;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.queryParam;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

import java.time.Duration;
import java.time.Instant;
import kr.mujuthaek.api.common.exception.CustomException;
import kr.mujuthaek.api.notice.client.ExtractionReviewClient;
import kr.mujuthaek.api.notice.client.ExtractionReviewProperties;
import kr.mujuthaek.api.notice.dto.response.AdminReviewQueueResponse.Item;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;

/** 검수 대기열 무한 스크롤: 공고·혜택을 들어온 시각 순으로 섞고, 쪽마다 커서로 이어 받아요. 가짜 검수 API를 써요. */
class AdminReviewQueueTest {

  private static final String BASE = "http://extraction.test";
  private static final String N1 = "11111111-1111-1111-1111-111111111111";
  private static final String N2 = "22222222-2222-2222-2222-222222222222";
  private static final String B1 = "33333333-3333-3333-3333-333333333333";
  private static final String B2 = "44444444-4444-4444-4444-444444444444";

  private MockRestServiceServer server;

  private AdminReviewService service() {
    var builder = RestClient.builder();
    server = MockRestServiceServer.bindTo(builder).build();
    var client =
        new ExtractionReviewClient(
            new ExtractionReviewProperties(BASE, null, Duration.ofSeconds(1)), builder);
    return new AdminReviewService(
        client,
        java.time.Clock.fixed(Instant.parse("2026-10-29T03:00:00Z"), java.time.ZoneOffset.UTC));
  }

  private static String notices(int total, boolean more, String... rows) {
    return "{\"total\":%d,\"hasMore\":%b,\"items\":[%s]}"
        .formatted(total, more, String.join(",", rows));
  }

  private static String notice(String id, String at) {
    return """
        {"jobId":"%s","jobStatus":"IN_REVIEW","title":"가상 공고 %s","sourceCode":"lh_myhome",
         "rawVersion":1,"queuedAt":"%s","reasons":[]}"""
        .formatted(id, id.substring(0, 1), at);
  }

  private static String benefit(String id, String at, boolean reported) {
    return """
        {"reviewId":"%s","title":"가상 혜택 %s","sourceCode":"youth","rawVersion":2,
         "queuedAt":"%s","reported":%b}"""
        .formatted(id, id.substring(0, 1), at, reported);
  }

  private void respond(String path, String body) {
    server
        .expect(requestTo(startsWith(BASE + path + "?status=PENDING&limit=2")))
        .andRespond(withSuccess(body, MediaType.APPLICATION_JSON));
  }

  @Test
  void mergesNoticesAndBenefitsByQueuedTimeAndContinuesEachSideFromItsCursor() {
    var service = service();
    // 공고 01:00·03:00, 혜택 02:00·04:00 → 01:00 공고, 02:00 혜택 / 03:00 공고, 04:00 혜택
    respond(
        "/reviews",
        notices(
            2,
            false,
            notice(N1, "2026-10-29 01:00:00.123456+00:00"),
            notice(N2, "2026-10-29 03:00:00+00:00")));
    respond(
        "/benefit-reviews",
        notices(
            2,
            false,
            benefit(B1, "2026-10-29 02:00:00+00:00", false),
            benefit(B2, "2026-10-29 04:00:00+00:00", true)));
    var first = service.queue(null, null, null, 2);
    server.verify();

    assertThat(first.items()).extracting(Item::id).containsExactly(N1, B1);
    assertThat(first.items()).extracting(Item::kind).containsExactly("NOTICE", "BENEFIT");
    assertThat(first.items()).extracting(Item::reason).containsExactly("MUST", "CHECK");
    assertThat(first.total()).isEqualTo(4);
    assertThat(first.nextCursor()).isNotNull();

    // 다음 페이지: 쪽마다 보낸 마지막 건 다음부터 (시각은 마이크로초까지 UTC로)
    server.reset();
    server
        .expect(requestTo(startsWith(BASE + "/reviews?status=PENDING&limit=2")))
        .andExpect(queryParam("afterAt", "2026-10-29T01%3A00%3A00.123456Z")) // 주소에서 풀면 그대로예요
        .andExpect(queryParam("afterId", N1))
        .andRespond(
            withSuccess(
                notices(2, false, notice(N2, "2026-10-29 03:00:00+00:00")),
                MediaType.APPLICATION_JSON));
    server
        .expect(requestTo(startsWith(BASE + "/benefit-reviews?status=PENDING&limit=2")))
        .andExpect(queryParam("afterId", B1))
        .andRespond(
            withSuccess(
                notices(2, false, benefit(B2, "2026-10-29 04:00:00+00:00", true)),
                MediaType.APPLICATION_JSON));
    var second = service.queue(null, null, first.nextCursor(), 2);
    server.verify();

    assertThat(second.items()).extracting(Item::id).containsExactly(N2, B2);
    assertThat(second.items().get(1).reason()).isEqualTo("MUST"); // 정책 제보로 다시 연 혜택
    assertThat(second.nextCursor()).isNull();
  }

  @Test
  void aSideWithMoreUpstreamKeepsGoingEvenIfThisPageTookAllItFetched() {
    var service = service();
    respond(
        "/reviews",
        notices(
            5,
            true,
            notice(N1, "2026-10-29 01:00:00+00:00"),
            notice(N2, "2026-10-29 02:00:00+00:00")));
    respond("/benefit-reviews", notices(0, false));
    var page = service.queue(null, null, null, 2);
    assertThat(page.items()).extracting(Item::id).containsExactly(N1, N2);
    assertThat(page.nextCursor()).isNotNull();

    // 혜택은 다 받았으니 다음 페이지에서는 부르지 않아요
    server.reset();
    server
        .expect(requestTo(startsWith(BASE + "/reviews?status=PENDING&limit=2")))
        .andExpect(queryParam("afterId", N2))
        .andRespond(withSuccess(notices(5, false), MediaType.APPLICATION_JSON));
    assertThat(service.queue(null, null, page.nextCursor(), 2).nextCursor()).isNull();
    server.verify();
  }

  @Test
  void kindsAndFormatReasonSkipBenefits() {
    var service = service();
    server
        .expect(requestTo(BASE + "/reviews?status=PENDING&limit=2&reason=FORMAT"))
        .andRespond(withSuccess(notices(0, false), MediaType.APPLICATION_JSON));
    assertThat(service.queue(null, "FORMAT", null, 2).items()).isEmpty();
    server.verify();

    server.reset();
    server
        .expect(requestTo(BASE + "/benefit-reviews?status=PENDING&limit=2&reported=true"))
        .andRespond(withSuccess(notices(0, false), MediaType.APPLICATION_JSON));
    assertThat(service.queue("BENEFIT", "MUST", null, 2).nextCursor()).isNull();
    server.verify();
  }

  @Test
  void rejectsBadInput() {
    var service = service();
    assertThatThrownBy(() -> service.queue("BOTH", null, null, 2))
        .isInstanceOf(CustomException.class);
    assertThatThrownBy(() -> service.queue(null, "NOPE", null, 2))
        .isInstanceOf(CustomException.class);
    assertThatThrownBy(() -> service.queue(null, null, null, 101))
        .isInstanceOf(CustomException.class);
    assertThatThrownBy(() -> service.queue(null, null, "not-a-cursor", 2))
        .isInstanceOf(CustomException.class);
  }

  @Test
  void firstPageIsReusedBrieflyAndRefetchedAfterADecision() {
    var service = service();
    // 받을 요청 차례: 첫 페이지(공고만) → 반려 → 남은 건수 → (처리했으니) 첫 페이지 다시. 더 받으면 가짜 서버가 실패시켜요
    respond("/reviews", notices(1, false, notice(N1, "2026-10-29 01:00:00+00:00")));
    server
        .expect(requestTo(BASE + "/reviews/" + N1 + "/reject"))
        .andRespond(withSuccess("{\"reviewStatus\":\"REJECTED\"}", MediaType.APPLICATION_JSON));
    server
        .expect(requestTo(BASE + "/reviews?status=PENDING&limit=1"))
        .andRespond(withSuccess(notices(0, false), MediaType.APPLICATION_JSON));
    respond("/reviews", notices(0, false));

    var first = service.queue("NOTICE", null, null, 2);
    assertThat(service.queue("NOTICE", null, "", 2)).isSameAs(first);
    service.reject(N1, null, "admin-1");
    assertThat(service.queue("NOTICE", null, null, 2).items()).isEmpty();
    server.verify();
  }

  @Test
  void cursorRoundTrips() {
    var cursor =
        new ReviewQueueCursor(
            new ReviewQueueCursor.Side(
                new ExtractionReviewClient.After(Instant.parse("2026-10-29T01:00:00.123456Z"), N1),
                false),
            ReviewQueueCursor.Side.DONE);
    assertThat(ReviewQueueCursor.decode(cursor.encode())).isEqualTo(cursor);
    assertThat(ReviewQueueCursor.decode(null)).isEqualTo(ReviewQueueCursor.START);
  }
}
