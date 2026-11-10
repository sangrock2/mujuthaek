package kr.mujuthaek.api.notification;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.IOException;
import java.io.InputStream;
import java.time.Instant;
import java.util.List;
import java.util.UUID;
import kr.mujuthaek.api.TestcontainersConfiguration;
import kr.mujuthaek.api.notice.domain.IngestionOutcome;
import kr.mujuthaek.api.notice.service.internal.NoticeIngestionService;
import kr.mujuthaek.api.user.domain.SocialProvider;
import kr.mujuthaek.api.user.repository.InterestRepository;
import kr.mujuthaek.api.user.service.FavoriteService;
import kr.mujuthaek.api.user.service.SocialLoginService;
import kr.mujuthaek.api.user.service.SocialProfile;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.simple.JdbcClient;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;
import tools.jackson.databind.node.ObjectNode;

/**
 * notice 정책 내부 이벤트(PolicyPublished·PolicyUpdated) → notification.requested (정책 저장과 같은 트랜잭션). 창업지원
 * 사업·사업공간 모집은 notice.policy_judgments에 있어요. 시계는 10/25, 픽스처 정책 신청은 10/7부터예요.
 */
@SpringBootTest(
    properties = {
      "app.outbox.scheduling-enabled=false",
      "spring.rabbitmq.listener.simple.auto-startup=false",
      "notice.status-refresh.enabled=false",
      "benefit.status-refresh.enabled=false",
      "notification.deadline-reminder.enabled=false",
      "app.notification.test-recipients[0].user-id=0192b6f0-0000-7000-8000-0000000000a1",
      "app.notification.test-recipients[0].email=me@example.com",
      "app.notification.test-recipients[0].quiet-enabled=false"
    })
@Import({TestcontainersConfiguration.class, NotificationTestClock.class})
class PolicyNotificationRequestTest {

  static final UUID ME = UUID.fromString("0192b6f0-0000-7000-8000-0000000000a1");

  @Autowired NoticeIngestionService ingestion;
  @Autowired JdbcClient jdbc;
  @Autowired JsonMapper json;
  @Autowired NotificationTestClock.MovableClock clock;
  @Autowired SocialLoginService logins;
  @Autowired InterestRepository interests;
  @Autowired FavoriteService favorites;

  @BeforeEach
  void clean() {
    clock.set("2026-10-25T12:00");
    jdbc.sql(
            "truncate notice.notice_reports, notice.notice_versions, notice.notice_posts,"
                + " notice.notice_follow_ups,"
                + " notice.notice_regions, notice.notice_source_heads,"
                + " notice.notice_duplicate_candidates, notice.notice_area_scores, notice.notices,"
                + " notice.extraction_results, notice.policy_duplicate_candidates, notice.policy_judgments,"
                + " common.processed_events")
        .update();
    jdbc.sql("delete from common.outbox").update();
    jdbc.sql("delete from notification.push_subscriptions").update();
    jdbc.sql("delete from notification.notifications").update();
    jdbc.sql("delete from account.business_interests").update();
    jdbc.sql("delete from account.favorites").update();
  }

  @Test
  void newStartupSupportGoesToBusinessInterestsAndCorrectionToFavorites() {
    Instant now = Instant.now();
    UUID everywhere = member(); // 전국 사업 포함 관심 + 기기
    UUID busanOnly = member(); // 부산만, 전국 빼기 → 전국 사업이라도 아님. 나중에 관심 정책으로 둠
    interests.saveBusiness(
        everywhere,
        new InterestRepository.Business(List.of("11000"), true, List.of(), List.of()),
        now);
    interests.saveBusiness(
        busanOnly,
        new InterestRepository.Business(List.of("26000"), false, List.of(), List.of()),
        now);
    subscribe(everywhere, "https://fcm.googleapis.com/fcm/send/everywhere");
    subscribe(busanOnly, "https://fcm.googleapis.com/fcm/send/busan");

    ObjectNode v2 = policy("STARTUP_SUPPORT", 2, "2026-11-02");
    UUID id = idOf(v2);
    assertThat(apply(v2)).isEqualTo(IngestionOutcome.POLICY_JUDGMENT_SAVED);

    assertThat(inboxUsers("STARTUP_SUPPORT:" + id + ":NEW"))
        .containsExactlyInAnyOrder(everywhere, ME);
    JsonNode created = onlyRequest();
    assertThat(created.path("type").asString()).isEqualTo("NEW_SUPPORT");
    assertThat(created.path("target").path("type").asString()).isEqualTo("STARTUP_SUPPORT");
    assertThat(created.path("target").path("id").asString()).isEqualTo(id.toString());
    assertThat(created.path("linkPath").asString()).isEqualTo("/business/support/" + id);
    assertThat(created.path("title").asString()).isEqualTo("새 창업지원: 청년 창업 지원사업");
    assertThat(created.path("body").asString())
        .isEqualTo("관심 조건에 맞는 새 창업지원 소식이에요. 창업진흥원 · 11월 2일 마감");
    assertThat(created.toString()).contains("fcm/send/everywhere").doesNotContain("busan");

    favorites.add(busanOnly, "startup-support", id);
    jdbc.sql("delete from common.outbox").update();
    ObjectNode v3 = samePolicy(v2, 3);
    ((ObjectNode) v3.path("payload").path("schedule")).put("applyEndOn", "2026-11-09");
    apply(v3);

    assertThat(inboxUsers("STARTUP_SUPPORT:" + id + ":CORRECTED:3"))
        .containsExactlyInAnyOrder(busanOnly, ME);
    JsonNode corrected = onlyRequest();
    assertThat(corrected.path("title").asString()).isEqualTo("정정: 청년 창업 지원사업");
    assertThat(corrected.path("body").asString()).isEqualTo("관심 창업지원의 일정 내용이 바뀌었어요.");
    assertThat(corrected.toString()).contains("fcm/send/busan").doesNotContain("everywhere");
  }

  @Test
  void aPolicyOpenUntilTheBudgetRunsOutSaysSoInTheNewPolicyAlert() {
    // 2026-11-10 재검토: 마감일 대신 「예산 소진 시까지」만 있는 정책은 알림 문구에 신청 기간 정보가 하나도 없었음
    ObjectNode policy = policy("STARTUP_SUPPORT", 2, null);
    ((ObjectNode) policy.path("payload")).put("applyNote", "예산 소진 시까지");

    apply(policy);

    assertThat(onlyRequest().path("body").asString())
        .isEqualTo("관심 조건에 맞는 새 창업지원 소식이에요. 창업진흥원 · 예산 소진 시까지");
  }

  @Test
  void spaceRecruitmentLinksToSpacesAndMatchesRegion() {
    Instant now = Instant.now();
    UUID seoul = member();
    UUID busan = member();
    interests.saveBusiness(
        seoul, new InterestRepository.Business(List.of("11680"), false, List.of(), List.of()), now);
    interests.saveBusiness(
        busan, new InterestRepository.Business(List.of("26000"), false, List.of(), List.of()), now);

    ObjectNode space = policy("SPACE_RECRUITMENT", 2, "2026-10-30", "11000");
    UUID id = idOf(space);
    apply(space);

    assertThat(inboxUsers("SPACE_RECRUITMENT:" + id + ":NEW"))
        .as("서울 전체 정책이라 강남구 관심 회원은 맞고 부산은 아님")
        .containsExactlyInAnyOrder(seoul, ME);
    var row =
        jdbc.sql(
                "select target_type, link_path from notification.notifications"
                    + " where user_id = :me and dedup_key like 'SPACE_RECRUITMENT:%'")
            .param("me", seoul)
            .query((rs, i) -> rs.getString(1) + " " + rs.getString(2))
            .single();
    assertThat(row).isEqualTo("SPACE_RECRUITMENT /business/spaces/" + id);
  }

  @Test
  void closedReprocessedAndInvisibleChangesAreNotAlerted() {
    apply(policy("STARTUP_SUPPORT", 2, "2026-10-20")); // 이미 마감
    ObjectNode reprocess = otherPolicy(policy("STARTUP_SUPPORT", 2, "2026-11-02"));
    ((ObjectNode) reprocess.path("payload")).put("reprocess", true);
    apply(reprocess);
    assertThat(requests()).isEmpty();
    assertThat(count("notification.notifications")).isZero();

    ObjectNode open = otherPolicy(policy("STARTUP_SUPPORT", 2, "2026-11-02"));
    apply(open);
    favorites.add(member(), "STARTUP_SUPPORT", idOf(open));
    jdbc.sql("delete from common.outbox").update();
    ObjectNode renamed = samePolicy(open, 3);
    ((ObjectNode) renamed.path("payload")).put("title", "이름만 바뀐 사업");
    apply(renamed);
    assertThat(requests()).as("제목·지역만 바뀐 정정은 알리지 않아요").isEmpty();
  }

  // ---------- 도움 ----------

  private UUID member() {
    return logins
        .login(new SocialProfile(SocialProvider.KAKAO, "policy-" + UUID.randomUUID(), "닉네임"))
        .userId();
  }

  private void subscribe(UUID userId, String endpoint) {
    jdbc.sql(
            """
            insert into notification.push_subscriptions
                (id, user_id, endpoint, p256dh, auth, created_at, updated_at)
            values (:id, :userId, :endpoint, 'p256dh', 'auth', now(), now())
            """)
        .param("id", UUID.randomUUID())
        .param("userId", userId)
        .param("endpoint", endpoint)
        .update();
  }

  /** NoticeIngestionIntegrationTest와 같은 정책 판정 틀 결과 (창업지원·사업공간 모집). 기관은 창업진흥원. */
  private ObjectNode policy(String field, int version, String applyEnd, String... regions) {
    ObjectNode event = fixture();
    event.put("eventId", UUID.randomUUID().toString());
    ObjectNode payload = (ObjectNode) event.path("payload");
    payload.put("field", field);
    payload.put("rawVersion", version);
    payload.put("reviewStatus", "AUTO_PASSED");
    payload.put("title", "청년 창업 지원사업");
    payload.remove("notice");
    payload.remove("heldItems");
    payload.putArray("conditions");
    payload.putArray("applicationWindows");
    payload.putNull("regionCode");
    ObjectNode schedule = payload.putObject("schedule");
    schedule.put("applyStartOn", "2026-10-07");
    schedule.put("applyEndOn", applyEnd);
    var codes = payload.putArray("regionCodes");
    for (String region : regions) codes.add(region);
    payload.put(
        "detailUrl", "https://www.k-startup.go.kr/web/contents/bizpbanc-ongoing.do?pbancSn=1");
    payload.put("applyAlways", false);
    payload
        .putObject("policyInfo")
        .put("organization", "창업진흥원")
        .putNull("supportArea")
        .putNull("summary")
        .putNull("contact")
        .putNull("applyMethod")
        .putNull("applyUrl")
        .putNull("guideUrl")
        .putNull("amountText");
    boolean startup = field.equals("STARTUP_SUPPORT");
    ObjectNode frame = payload.putObject("judgment");
    frame.put("schema", startup ? "startup-support-judgment.v1" : "business-space-judgment.v1");
    frame.put(startup ? "rawPolicyId" : "rawPostId", payload.path("rawPostId").asString());
    frame.put("rawVersion", version);
    if (startup) frame.putNull("referenceDate");
    else frame.put("referenceDate", "2026-10-07");
    frame.putArray("common");
    frame.putArray("groups").addObject().put("id", "all").put("name", "전체").putArray("criteria");
    frame.putArray("preferences");
    frame.putArray("notes");
    return event;
  }

  /** 같은 정책의 다음 수집 버전 (새 eventId). */
  private static ObjectNode samePolicy(ObjectNode base, int version) {
    ObjectNode event = base.deepCopy();
    event.put("eventId", UUID.randomUUID().toString());
    ((ObjectNode) event.path("payload")).put("rawVersion", version);
    ((ObjectNode) event.path("payload").path("judgment")).put("rawVersion", version);
    return event;
  }

  /** 다른 정책으로 (새 정책 ID, 틀의 원본 ID도 같이). */
  private static ObjectNode otherPolicy(ObjectNode event) {
    String id = UUID.randomUUID().toString();
    ((ObjectNode) event.path("payload")).put("rawPostId", id);
    ObjectNode frame = (ObjectNode) event.path("payload").path("judgment");
    frame.put(frame.has("rawPolicyId") ? "rawPolicyId" : "rawPostId", id);
    return event;
  }

  private static UUID idOf(ObjectNode event) {
    return UUID.fromString(event.path("payload").path("rawPostId").asString());
  }

  private IngestionOutcome apply(ObjectNode event) {
    return ingestion.apply(json.writeValueAsString(event));
  }

  private ObjectNode fixture() {
    try (InputStream in =
        getClass().getResourceAsStream("/notice/extraction-completed-seoripul.json")) {
      return (ObjectNode) json.readTree(in);
    } catch (IOException e) {
      throw new IllegalStateException(e);
    }
  }

  private List<UUID> inboxUsers(String dedupKey) {
    return jdbc.sql("select user_id from notification.notifications where dedup_key = :k")
        .param("k", dedupKey)
        .query(UUID.class)
        .list();
  }

  private long count(String table) {
    return jdbc.sql("select count(*) from " + table).query(Long.class).single();
  }

  private JsonNode onlyRequest() {
    List<JsonNode> all = requests();
    assertThat(all).hasSize(1);
    return all.getFirst();
  }

  private List<JsonNode> requests() {
    return jdbc
        .sql(
            "select payload::text from common.outbox where event_type = 'notification.requested'"
                + " order by created_at")
        .query(String.class)
        .list()
        .stream()
        .map(s -> json.readTree(s).path("payload"))
        .toList();
  }
}
