package kr.mujuthaek.api.notification;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.doReturn;
import static org.mockito.Mockito.doThrow;

import java.io.IOException;
import java.io.InputStream;
import java.time.Instant;
import java.util.List;
import java.util.UUID;
import kr.mujuthaek.api.TestcontainersConfiguration;
import kr.mujuthaek.api.notice.NoticeFixtures;
import kr.mujuthaek.api.notice.domain.IngestionOutcome;
import kr.mujuthaek.api.notice.service.internal.NoticeIngestionService;
import kr.mujuthaek.api.notification.service.internal.Recipient;
import kr.mujuthaek.api.notification.service.internal.RecipientFinder;
import kr.mujuthaek.api.user.domain.SocialProvider;
import kr.mujuthaek.api.user.repository.FavoriteRepository;
import kr.mujuthaek.api.user.repository.InterestRepository;
import kr.mujuthaek.api.user.repository.NotificationSettingRepository;
import kr.mujuthaek.api.user.service.SocialLoginService;
import kr.mujuthaek.api.user.service.SocialProfile;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;
import tools.jackson.databind.node.ObjectNode;

/**
 * notice 내부 이벤트 → notification.requested (공고 저장과 같은 트랜잭션). 서리풀 공고 접수는 10/26~10/30이고 시계는 10/25예요.
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
class NoticeNotificationRequestTest {

  @Autowired NoticeIngestionService ingestion;
  @Autowired JdbcClient jdbc;
  @Autowired JsonMapper json;
  @Autowired NotificationTestClock.MovableClock clock;
  @MockitoSpyBean RecipientFinder recipients;
  @Autowired SocialLoginService logins;
  @Autowired InterestRepository interests;
  @Autowired NotificationSettingRepository settings;
  @Autowired FavoriteRepository favorites;

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
    jdbc.sql("delete from account.housing_interests").update();
    jdbc.sql("delete from account.favorites").update();
  }

  @Test
  void realMembersAreChosenByInterestsFavoritesAndSettings() {
    Instant now = Instant.now();
    UUID seocho = member(); // 서초구 관심 + 기기
    UUID seoulOff = member(); // 서울 전체 관심, 새 공고 알림 끔 + 기기
    UUID busan = member(); // 부산 관심 → 이 공고는 아님. 나중에 관심 공고로 둠
    interests.saveHousing(
        seocho, new InterestRepository.Housing(List.of("11650"), false, List.of()), now);
    interests.saveHousing(
        seoulOff, new InterestRepository.Housing(List.of("11000"), false, List.of()), now);
    interests.saveHousing(
        busan, new InterestRepository.Housing(List.of("26350"), false, List.of()), now);
    settings.save(
        seoulOff,
        new NotificationSettingRepository.Settings(false, true, true, true, true, false),
        now);
    subscribe(seocho, "https://fcm.googleapis.com/fcm/send/seocho", "2026-10-25T00:00:00Z");
    subscribe(seoulOff, "https://fcm.googleapis.com/fcm/send/seoul-off", "2026-10-25T00:00:00Z");
    subscribe(busan, "https://fcm.googleapis.com/fcm/send/busan", "2026-10-25T00:00:00Z");

    apply(fixture());

    UUID id = onlyNotice();
    assertThat(inboxUsers("NOTICE:" + id + ":NEW"))
        .as("관심 지역이 맞는 회원 + 테스트 회원 (알림을 끈 회원도 알림함에는)")
        .containsExactlyInAnyOrder(seocho, seoulOff, ME);
    assertThat(recipientIds(onlyRequest()))
        .as("새 공고 알림을 끈 회원은 보내지 않음")
        .containsExactlyInAnyOrder(seocho.toString(), ME.toString());

    favorites.add(busan, "NOTICE", id, now);
    jdbc.sql("delete from common.outbox").update();
    apply(correctionOf(fixture(), "2026-11-07"));

    assertThat(inboxUsers("NOTICE:" + id + ":CORRECTED:2")).containsExactlyInAnyOrder(busan, ME);
    JsonNode corrected = onlyRequest();
    assertThat(recipientIds(corrected)).containsExactlyInAnyOrder(busan.toString(), ME.toString());
    assertThat(corrected.toString()).contains("fcm/send/busan").doesNotContain("seocho");
  }

  @Test
  void aMemberWhoChoseACityWithDistrictsGetsNoticesOfItsDistricts() {
    // 2026-11-10 재검토: 관심 지역 수원시(41110)를 고른 회원에게 장안구(41111) 새 공고 알림이 빠졌음
    Instant now = Instant.now();
    UUID suwon = member();
    UUID jangan = member();
    UUID gwonseon = member();
    interests.saveHousing(
        suwon, new InterestRepository.Housing(List.of("41110"), false, List.of()), now);
    interests.saveHousing(
        jangan, new InterestRepository.Housing(List.of("41111"), false, List.of()), now);
    interests.saveHousing(
        gwonseon, new InterestRepository.Housing(List.of("41113"), false, List.of()), now);
    ObjectNode payload = fixture();
    NoticeFixtures.region((ObjectNode) payload.get("payload"), "41111");

    apply(payload);

    assertThat(inboxUsers("NOTICE:" + onlyNotice() + ":NEW"))
        .containsExactlyInAnyOrder(suwon, jangan, ME);
  }

  private UUID member() {
    return logins
        .login(new SocialProfile(SocialProvider.KAKAO, "rcpt-" + UUID.randomUUID(), "닉네임"))
        .userId();
  }

  private List<UUID> inboxUsers(String dedupKey) {
    return jdbc.sql("select user_id from notification.notifications where dedup_key = :k")
        .param("k", dedupKey)
        .query(UUID.class)
        .list();
  }

  private static List<String> recipientIds(JsonNode request) {
    List<String> ids = new java.util.ArrayList<>();
    request.path("recipients").forEach(r -> ids.add(r.path("userId").asString()));
    return ids;
  }

  @Test
  void everyRecipientGetsAnInboxEntryEvenWithoutAnyChannel() {
    UUID silent = UUID.randomUUID(); // 기기·이메일 없음
    UUID off = UUID.randomUUID(); // 이 종류를 끔 (기기는 있음)
    subscribe(off, "https://fcm.googleapis.com/fcm/send/off", "2026-10-25T00:00:00Z");
    doReturn(List.of(Recipient.push(silent, false), new Recipient(off, null, false, false)))
        .when(recipients)
        .forNewNotice(any(), any(), any(Boolean.class), any());

    apply(fixture());

    UUID id = onlyNotice();
    assertThat(
            jdbc.sql(
                    "select user_id from notification.notifications where dedup_key = :k order by user_id")
                .param("k", "NOTICE:" + id + ":NEW")
                .query(UUID.class)
                .list())
        .containsExactlyInAnyOrder(silent, off, ME);
    assertThat(
            jdbc.sql("select title from notification.notifications where user_id = :u")
                .param("u", silent)
                .query(String.class)
                .single())
        .isEqualTo("새 공고: 서초구 서리풀 청년아트타운 잔여세대 입주자 모집공고");
    JsonNode request = onlyRequest();
    assertThat(request.path("recipients"))
        .as("보낼 채널이 없는 회원은 요청에서 빠져요 (관심 공고로 둔 테스트 회원만)")
        .hasSize(1);
    assertThat(request.path("recipients").get(0).path("userId").asString())
        .isEqualTo(ME.toString());
  }

  @Test
  void newNoticeBecomesNewNoticeRequest() {
    assertThat(apply(fixture())).isEqualTo(IngestionOutcome.PUBLISHED);

    JsonNode p = onlyRequest();
    UUID id = onlyNotice();
    assertThat(p.path("type").asString()).isEqualTo("NEW_NOTICE");
    assertThat(p.path("dedupKey").asString()).isEqualTo("NOTICE:" + id + ":NEW");
    assertThat(p.path("target").path("type").asString()).isEqualTo("NOTICE");
    assertThat(p.path("linkPath").asString()).isEqualTo("/notices/" + id);
    assertThat(p.path("title").asString()).isEqualTo("새 공고: 서초구 서리풀 청년아트타운 잔여세대 입주자 모집공고");
    assertThat(p.path("body").asString())
        .startsWith("관심 조건에 맞는 새 공고 소식이에요.")
        .endsWith("10월 30일 마감");
    assertThat(p.path("recipients")).as("관심 조건·관심 공고 둘 다 걸려도 한 번").hasSize(1);
    assertThat(p.path("recipients").get(0).path("email").asString()).isEqualTo("me@example.com");
    assertThat(p.path("recipients").get(0).path("push").isNull()).as("구독 기기 없음").isTrue();
  }

  @Test
  void recipientCarriesTheirFiveMostRecentPushDevices() {
    for (int i = 1; i <= 6; i++) { // 6대: 1번이 가장 오래됨 (5대 제한을 넘은 상태도 요청에는 5대만)
      subscribe(ME, "https://fcm.googleapis.com/fcm/send/me-" + i, "2026-10-2" + i + "T00:00:00Z");
    }
    subscribe(
        UUID.randomUUID(), "https://fcm.googleapis.com/fcm/send/other", "2026-10-25T00:00:00Z");

    apply(fixture());

    JsonNode push = onlyRequest().path("recipients").get(0).path("push");
    assertThat(push).hasSize(5);
    assertThat(push.get(0).path("endpoint").asString())
        .as("최근에 쓴 기기부터")
        .isEqualTo("https://fcm.googleapis.com/fcm/send/me-6");
    assertThat(push.get(0).path("p256dh").asString()).isEqualTo("p256dh-me-6");
    assertThat(push.get(0).path("auth").asString()).isEqualTo("auth-me-6");
    assertThat(push.get(0).propertyNames()).containsExactlyInAnyOrder("endpoint", "p256dh", "auth");
    assertThat(push.toString()).doesNotContain("me-1").doesNotContain("other");
  }

  @Test
  void correctionBecomesCorrectedRequestForThatVersion() {
    ObjectNode original = fixture();
    apply(original);
    jdbc.sql("delete from common.outbox").update();

    assertThat(apply(correctionOf(fixture(), "2026-11-07")))
        .isEqualTo(IngestionOutcome.NEW_VERSION);

    JsonNode p = onlyRequest();
    UUID id = onlyNotice();
    assertThat(p.path("type").asString()).isEqualTo("CORRECTED");
    assertThat(p.path("dedupKey").asString()).isEqualTo("NOTICE:" + id + ":CORRECTED:2");
    assertThat(p.path("title").asString()).isEqualTo("정정: 서초구 서리풀 청년아트타운 잔여세대 입주자 모집공고");
    assertThat(p.path("body").asString())
        .startsWith("관심 공고의 ")
        .contains("일정")
        .endsWith(" 내용이 바뀌었어요.");
  }

  @Test
  void followUpBecomesFollowUpRequestOncePerPost() {
    apply(fixture());
    jdbc.sql("delete from common.outbox").update();
    ObjectNode followUp = followUpOf(fixture(), "서류 제출 안내");
    String postId = followUp.path("payload").path("rawPostId").asString();

    assertThat(apply(followUp)).isEqualTo(IngestionOutcome.FOLLOW_UP_ATTACHED);

    JsonNode p = onlyRequest();
    UUID id = onlyNotice();
    assertThat(p.path("type").asString()).isEqualTo("FOLLOW_UP");
    assertThat(p.path("dedupKey").asString()).isEqualTo("NOTICE:" + id + ":FOLLOW_UP:" + postId);
    assertThat(p.path("title").asString()).isEqualTo("후속 안내: 서초구 서리풀 청년아트타운 잔여세대 입주자 모집공고");
    assertThat(p.path("body").asString()).isEqualTo("관심 공고에 '서류 제출 안내' (10월 16일) 안내가 올라왔어요.");

    // 같은 후속 글이 새 버전으로 바뀌면 같은 키 → 알림 서버가 한 번만 보내요
    jdbc.sql("delete from common.outbox").update();
    ObjectNode changed = followUp.deepCopy();
    changed.put("eventId", UUID.randomUUID().toString());
    ((ObjectNode) changed.path("payload")).put("rawVersion", 2);
    ((ObjectNode) changed.path("payload").path("notice").path("input")).put("rawVersion", 2);
    ObjectNode ref =
        (ObjectNode) changed.path("payload").path("notice").path("sourceReferences").get(0);
    ref.put("rawVersion", 2);
    ref.put("sourceTitle", "서류 제출 안내 (기한 연장)");
    apply(changed);
    assertThat(requests())
        .extracting(r -> r.path("dedupKey").asString())
        .containsOnly("NOTICE:" + id + ":FOLLOW_UP:" + postId);
  }

  @Test
  void reprocessAndClosedNoticesAreNotAlerted() {
    ObjectNode reprocess = fixture();
    ((ObjectNode) reprocess.path("payload")).put("reprocess", true);
    ((ObjectNode) reprocess.path("payload").path("notice").path("input")).put("reprocess", true);
    apply(reprocess);
    assertThat(requests()).as("재처리").isEmpty();

    clean();
    clock.set("2026-11-02T12:00"); // 10/30 마감 뒤에 처음 받음
    apply(fixture());
    assertThat(requests()).as("이미 마감").isEmpty();
  }

  @Test
  void failureRollsBackTheNoticeSoItIsRetried() {
    doThrow(new IllegalStateException("회원 조회 실패"))
        .when(recipients)
        .forNewNotice(any(), any(), any(Boolean.class), any());

    assertThatThrownBy(() -> apply(fixture())).isInstanceOf(IllegalStateException.class);
    assertThat(jdbc.sql("select count(*) from notice.notices").query(Long.class).single())
        .as("공고 저장도 되돌려져 다시 받을 때 알림 요청이 만들어져요")
        .isZero();
  }

  static final UUID ME = UUID.fromString("0192b6f0-0000-7000-8000-0000000000a1");

  private void subscribe(UUID userId, String endpoint, String at) {
    String name = endpoint.substring(endpoint.lastIndexOf('/') + 1);
    jdbc.sql(
            """
            insert into notification.push_subscriptions
                (id, user_id, endpoint, p256dh, auth, created_at, updated_at)
            values (:id, :userId, :endpoint, :p256dh, :auth, :at::timestamptz, :at::timestamptz)
            """)
        .param("id", UUID.randomUUID())
        .param("userId", userId)
        .param("endpoint", endpoint)
        .param("p256dh", "p256dh-" + name)
        .param("auth", "auth-" + name)
        .param("at", at)
        .update();
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

  /** NoticeIngestionIntegrationTest와 같은 정정 공고: 다른 원본 글이 원래 글을 가리키고 마감일을 바꿔요. */
  private static ObjectNode correctionOf(ObjectNode original, String newApplyEndOn) {
    String originalPostId = original.path("payload").path("rawPostId").asString();
    String correctionPostId = UUID.randomUUID().toString();
    original.put("eventId", UUID.randomUUID().toString());
    ObjectNode payload = (ObjectNode) original.path("payload");
    payload.put("rawPostId", correctionPostId);
    ((ObjectNode) payload.path("notice").path("input")).put("rawPostId", correctionPostId);
    ((ObjectNode) payload.path("schedule")).put("applyEndOn", newApplyEndOn);
    ((ObjectNode) payload.path("applicationWindows").get(0)).put("applyEndOn", newApplyEndOn);
    for (JsonNode schedule : payload.path("notice").path("schedules")) {
      if (schedule.path("kinds").toString().contains("APPLICATION")) {
        ((ObjectNode) schedule)
            .putObject("endsAt")
            .put("precision", "DAY")
            .put("value", newApplyEndOn);
      }
    }
    ObjectNode reference = (ObjectNode) payload.path("notice").path("sourceReferences").get(0);
    reference.put("rawPostId", correctionPostId);
    reference.put("kind", "CORRECTION");
    reference.put("supersedesPostId", originalPostId);
    return original;
  }

  private static ObjectNode followUpOf(ObjectNode original, String title) {
    ObjectNode followUp = correctionOf(original, "2026-10-30");
    ObjectNode reference =
        (ObjectNode) followUp.path("payload").path("notice").path("sourceReferences").get(0);
    reference.put("kind", "FOLLOW_UP");
    reference.put("sourceTitle", title);
    return followUp;
  }

  private UUID onlyNotice() {
    return jdbc.sql("select id from notice.notices").query(UUID.class).single();
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
