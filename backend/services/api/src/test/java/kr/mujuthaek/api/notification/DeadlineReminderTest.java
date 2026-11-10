package kr.mujuthaek.api.notification;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.doCallRealMethod;
import static org.mockito.Mockito.doThrow;

import java.util.List;
import java.util.OptionalInt;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import kr.mujuthaek.api.TestcontainersConfiguration;
import kr.mujuthaek.api.benefit.BenefitFixture;
import kr.mujuthaek.api.benefit.service.internal.BenefitIngestionService;
import kr.mujuthaek.api.notification.service.internal.DeadlineReminderService;
import kr.mujuthaek.api.notification.service.internal.RecipientFinder;
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

/** 마감 D-3·D-1: 하루 한 번, 11:00 뒤 따라잡기, 여러 서버, 실패 뒤 다시. 픽스처 신청 기간은 10/1~11/30이에요. */
@SpringBootTest(
    properties = {
      "app.outbox.scheduling-enabled=false",
      "benefit.status-refresh.enabled=false",
      "notification.deadline-reminder.enabled=false", // 테스트에서 직접 불러요
      "app.notification.test-recipients[0].user-id=0192b6f0-0000-7000-8000-0000000000a1",
      "app.notification.test-recipients[0].email=me@example.com",
      "app.notification.test-recipients[0].quiet-enabled=false"
    })
@Import({TestcontainersConfiguration.class, NotificationTestClock.class})
class DeadlineReminderTest {

  @Autowired DeadlineReminderService reminders;
  @Autowired BenefitIngestionService ingestion;
  @Autowired kr.mujuthaek.api.notice.service.internal.NoticeIngestionService noticeIngestion;
  @Autowired JdbcClient jdbc;
  @Autowired JsonMapper json;
  @Autowired NotificationTestClock.MovableClock clock;
  @MockitoSpyBean RecipientFinder recipients;

  @BeforeEach
  void clear() {
    clock.set("2026-10-25T12:00");
    jdbc.sql("delete from benefit.benefits").update();
    jdbc.sql("delete from notification.reminder_runs").update();
    jdbc.sql(
            "truncate notice.notice_reports, notice.notice_versions, notice.notice_posts,"
                + " notice.notice_follow_ups,"
                + " notice.notice_regions, notice.notice_source_heads,"
                + " notice.notice_duplicate_candidates, notice.notice_area_scores, notice.notices,"
                + " notice.extraction_results, notice.policy_duplicate_candidates, notice.policy_judgments")
        .update();
  }

  @Test
  void closingNoticesAreRemindedToo() throws Exception {
    // 서리풀 공고: 접수 10/26~10/30
    try (var in = getClass().getResourceAsStream("/notice/extraction-completed-seoripul.json")) {
      noticeIngestion.apply(new String(in.readAllBytes(), java.nio.charset.StandardCharsets.UTF_8));
    }
    UUID notice = onlyId("notice.notices");
    jdbc.sql("delete from common.outbox").update();

    clock.set("2026-10-27T11:00"); // D-3 = 10/30

    assertThat(reminders.runIfDue()).isEqualTo(OptionalInt.of(1));
    JsonNode d3 = byType(requests(), "DEADLINE_D3");
    assertThat(d3.path("dedupKey").asString()).isEqualTo("NOTICE:" + notice + ":D3:2026-10-30");
    assertThat(d3.path("title").asString()).isEqualTo("마감 3일 전: 서초구 서리풀 청년아트타운 잔여세대 입주자 모집공고");
    assertThat(d3.path("body").asString()).isEqualTo("관심 공고 접수가 10월 30일에 마감돼요.");
    assertThat(d3.path("linkPath").asString()).isEqualTo("/notices/" + notice);
    assertThat(d3.path("target").path("type").asString()).isEqualTo("NOTICE");
    assertThat(
            jdbc.sql("select count(*) from notification.notifications where dedup_key = :k")
                .param("k", "NOTICE:" + notice + ":D3:2026-10-30")
                .query(Long.class)
                .single())
        .as("알림함에도")
        .isEqualTo(1L);

    clock.set("2026-10-26T11:00");
    jdbc.sql("delete from notification.reminder_runs").update();
    jdbc.sql("delete from common.outbox").update();
    assertThat(reminders.runIfDue()).as("D-4는 아님").isEqualTo(OptionalInt.of(0));
  }

  @Test
  void closingStartupSupportAndSpaceRecruitmentAreRemindedToo() throws Exception {
    // notice.policy_judgments의 창업지원 사업(10/30 마감)·사업공간 모집(10/28 마감), 신청은 10/7부터
    UUID startup = noticePolicy("STARTUP_SUPPORT", "2026-10-30");
    UUID space = noticePolicy("SPACE_RECRUITMENT", "2026-10-28");
    jdbc.sql("delete from common.outbox").update();

    clock.set("2026-10-27T11:00"); // D-3 = 10/30, D-1 = 10/28

    assertThat(reminders.runIfDue()).isEqualTo(OptionalInt.of(2));
    JsonNode d3 = byType(requests(), "DEADLINE_D3");
    assertThat(d3.path("dedupKey").asString())
        .isEqualTo("STARTUP_SUPPORT:" + startup + ":D3:2026-10-30");
    assertThat(d3.path("target").path("type").asString()).isEqualTo("STARTUP_SUPPORT");
    assertThat(d3.path("linkPath").asString()).isEqualTo("/business/support/" + startup);
    assertThat(d3.path("body").asString()).isEqualTo("관심 창업지원 접수가 10월 30일에 마감돼요.");
    JsonNode d1 = byType(requests(), "DEADLINE_D1");
    assertThat(d1.path("dedupKey").asString())
        .isEqualTo("SPACE_RECRUITMENT:" + space + ":D1:2026-10-28");
    assertThat(d1.path("linkPath").asString()).isEqualTo("/business/spaces/" + space);
    assertThat(d1.path("body").asString()).isEqualTo("관심 사업공간 모집 접수가 내일(10월 28일) 마감돼요.");
  }

  @Test
  void threeAndOneDayBeforeDeadlineAreRequestedOnceADay() {
    UUID policy = policy(p -> {}); // 마감 11/30
    UUID other =
        policy(
            p -> {
              p.withObject("source").put("title", "청년 전세 이자 지원");
              p.withObject("schedule").put("applyEnd", "2026-11-28");
            });
    jdbc.sql("delete from common.outbox").update();

    clock.set("2026-11-27T10:59");
    assertThat(reminders.runIfDue()).as("11:00 전").isEmpty();

    clock.set("2026-11-27T11:00");
    assertThat(reminders.runIfDue()).isEqualTo(OptionalInt.of(2));
    List<JsonNode> sent = requests();
    JsonNode d3 = byType(sent, "DEADLINE_D3");
    assertThat(d3.path("dedupKey").asString()).isEqualTo("BENEFIT:" + policy + ":D3:2026-11-30");
    assertThat(d3.path("title").asString()).isEqualTo("마감 3일 전: 청년 취업자 주거비 지원사업");
    assertThat(d3.path("body").asString()).isEqualTo("관심 지원 정책 접수가 11월 30일에 마감돼요.");
    assertThat(d3.path("linkPath").asString()).isEqualTo("/benefits/" + policy);
    JsonNode d1 = byType(sent, "DEADLINE_D1");
    assertThat(d1.path("dedupKey").asString()).isEqualTo("BENEFIT:" + other + ":D1:2026-11-28");
    assertThat(d1.path("title").asString()).isEqualTo("내일 마감: 청년 전세 이자 지원");
    assertThat(d1.path("body").asString()).isEqualTo("관심 지원 정책 접수가 내일(11월 28일) 마감돼요.");
    assertThat(d1.path("target").path("type").asString()).isEqualTo("BENEFIT");
    assertThat(d1.path("recipients").get(0).path("email").asString()).isEqualTo("me@example.com");

    clock.set("2026-11-27T21:00");
    assertThat(reminders.runIfDue()).as("같은 날 두 번째 확인").isEmpty();
    assertThat(requests()).hasSize(2);

    clock.set("2026-11-29T11:10");
    assertThat(reminders.runIfDue()).isEqualTo(OptionalInt.of(1));
    assertThat(requests())
        .extracting(r -> r.path("dedupKey").asString())
        .contains("BENEFIT:" + policy + ":D1:2026-11-30");
  }

  @Test
  void serverDownAtNineCatchesUpLaterThatDay() {
    policy(p -> {});
    jdbc.sql("delete from common.outbox").update();

    clock.set("2026-11-29T23:55"); // 11:00부터 꺼져 있다가 밤에 켜짐

    assertThat(reminders.runIfDue()).isEqualTo(OptionalInt.of(1));
    assertThat(byType(requests(), "DEADLINE_D1")).isNotNull();
  }

  @Test
  void hiddenAlwaysNotStartedAndOtherDatesAreLeftOut() {
    policy(p -> p.put("relevant", false));
    policy(p -> p.withObject("schedule").put("applyAlways", true));
    policy(p -> p.withObject("schedule").put("applyStart", "2026-11-28"));
    policy(p -> p.withObject("schedule").put("applyEnd", "2026-11-29"));
    jdbc.sql("delete from common.outbox").update();

    clock.set("2026-11-27T11:00"); // D-3 = 11/30, D-1 = 11/28

    assertThat(reminders.runIfDue()).isEqualTo(OptionalInt.of(0));
    assertThat(requests()).isEmpty();
    assertThat(
            jdbc.sql("select requested from notification.reminder_runs")
                .query(Integer.class)
                .single())
        .as("보낼 것이 없어도 그날 했다고 남겨요")
        .isZero();
  }

  @Test
  void twoServersAtNineMakeOneSetOfRequests() throws Exception {
    for (int i = 0; i < 5; i++) {
      policy(p -> {});
    }
    jdbc.sql("delete from common.outbox").update();
    clock.set("2026-11-27T11:00");
    CyclicBarrier together = new CyclicBarrier(2);
    ExecutorService pool = Executors.newFixedThreadPool(2);
    try {
      List<CompletableFuture<OptionalInt>> runs =
          List.of(
              CompletableFuture.supplyAsync(() -> runTogether(together), pool),
              CompletableFuture.supplyAsync(() -> runTogether(together), pool));
      int ran = 0;
      for (CompletableFuture<OptionalInt> run : runs) {
        if (run.get(30, TimeUnit.SECONDS).isPresent()) {
          ran++;
        }
      }
      assertThat(ran).as("한 서버만").isEqualTo(1);
    } finally {
      pool.shutdownNow();
    }
    assertThat(requests()).hasSize(5);
  }

  @Test
  void failureRollsBackTheRunSoItIsRetried() {
    policy(p -> {});
    jdbc.sql("delete from common.outbox").update();
    clock.set("2026-11-27T11:00");
    doThrow(new IllegalStateException("회원 조회 실패"))
        .when(recipients)
        .forFavorite(any(), any(), any());

    assertThatThrownBy(() -> reminders.runIfDue()).isInstanceOf(IllegalStateException.class);
    assertThat(
            jdbc.sql("select count(*) from notification.reminder_runs").query(Long.class).single())
        .as("실행 기록도 되돌려짐")
        .isZero();

    doCallRealMethod().when(recipients).forFavorite(any(), any(), any());
    clock.set("2026-11-27T11:10");
    assertThat(reminders.runIfDue()).isEqualTo(OptionalInt.of(1));
    assertThat(requests()).hasSize(1);
  }

  private OptionalInt runTogether(CyclicBarrier together) {
    try {
      together.await(10, TimeUnit.SECONDS);
    } catch (Exception e) {
      throw new IllegalStateException(e);
    }
    return reminders.runIfDue();
  }

  /** 혜택 하나를 저장하고 ID를 돌려줘요 (dev benefit 픽스처: 주거 혜택, 신청 10/1~11/30) */
  private UUID policy(java.util.function.Consumer<ObjectNode> change) {
    UUID raw = UUID.randomUUID();
    ingestion.apply(BenefitFixture.event(raw, 1, change));
    return jdbc.sql("select id from benefit.benefits where raw_policy_id = :raw")
        .param("raw", raw)
        .query(UUID.class)
        .single();
  }

  /** notice 정책 판정 틀 하나를 저장하고 정책 ID를 돌려줘요 (서리풀 픽스처를 정책 결과로 바꿈, 신청 10/7부터) */
  private UUID noticePolicy(String field, String applyEnd) throws Exception {
    ObjectNode event;
    try (var in = getClass().getResourceAsStream("/notice/extraction-completed-seoripul.json")) {
      event = (ObjectNode) json.readTree(in);
    }
    UUID id = UUID.randomUUID();
    event.put("eventId", UUID.randomUUID().toString());
    ObjectNode payload = (ObjectNode) event.path("payload");
    payload.put("rawPostId", id.toString());
    payload.put("field", field);
    payload.put("rawVersion", 1);
    payload.put("reviewStatus", "AUTO_PASSED");
    payload.remove("notice");
    payload.remove("heldItems");
    payload.putArray("conditions");
    payload.putArray("applicationWindows");
    payload.putNull("regionCode");
    payload.putObject("schedule").put("applyStartOn", "2026-10-07").put("applyEndOn", applyEnd);
    payload.putArray("regionCodes");
    payload.put("detailUrl", "https://www.k-startup.go.kr/web/contents/bizpbanc-ongoing.do");
    payload.put("applyAlways", false);
    boolean startup = field.equals("STARTUP_SUPPORT");
    ObjectNode frame = payload.putObject("judgment");
    frame.put("schema", startup ? "startup-support-judgment.v1" : "business-space-judgment.v1");
    frame.put(startup ? "rawPolicyId" : "rawPostId", id.toString());
    frame.put("rawVersion", 1);
    if (startup) frame.putNull("referenceDate");
    else frame.put("referenceDate", "2026-10-07");
    frame.putArray("common");
    frame.putArray("groups").addObject().put("id", "all").put("name", "전체").putArray("criteria");
    frame.putArray("preferences");
    frame.putArray("notes");
    noticeIngestion.apply(json.writeValueAsString(event));
    return id;
  }

  private UUID onlyId(String table) {
    return jdbc.sql("select id from " + table).query(UUID.class).single();
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

  private static JsonNode byType(List<JsonNode> sent, String type) {
    return sent.stream()
        .filter(r -> type.equals(r.path("type").asString()))
        .findFirst()
        .orElseThrow();
  }
}
