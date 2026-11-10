package kr.mujuthaek.api.notification;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.UUID;
import kr.mujuthaek.api.TestcontainersConfiguration;
import kr.mujuthaek.api.notice.dto.request.AdminReportResolveRequest;
import kr.mujuthaek.api.notice.dto.request.AdminReportResolveRequest.Result;
import kr.mujuthaek.api.notice.dto.request.NoticeReportRequest;
import kr.mujuthaek.api.notice.service.internal.NoticeIngestionService;
import kr.mujuthaek.api.notice.service.internal.NoticeReportService;
import kr.mujuthaek.api.user.domain.SocialProvider;
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

/** 관리자가 제보를 처리하고 답을 남기면 → 제보한 회원에게 REPORT_ANSWERED (제보 처리와 같은 트랜잭션). */
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
class ReportAnsweredNotificationRequestTest {

  @Autowired NoticeIngestionService ingestion;
  @Autowired NoticeReportService reports;
  @Autowired SocialLoginService logins;
  @Autowired JdbcClient jdbc;
  @Autowired JsonMapper json;
  @Autowired NotificationTestClock.MovableClock clock;

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
  }

  @Test
  void answeredReportGoesOnlyToTheReporter() throws Exception {
    UUID notice = seoripul();
    UUID reporter = member();
    subscribe(reporter);
    UUID report = reports.report(notice, deposit(), reporter.toString()).id();
    jdbc.sql("delete from common.outbox").update();

    reports.resolve(
        report,
        new AdminReportResolveRequest(Result.FIXED, "보증금을 2,600만 원으로 고쳤어요", null),
        "admin-1");

    String key = "NOTICE:" + notice + ":ANSWERED:NOTICE:" + report;
    assertThat(
            jdbc.sql(
                    "select user_id from notification.notifications where type = 'REPORT_ANSWERED'"
                        + " and dedup_key = :k")
                .param("k", key)
                .query(UUID.class)
                .list())
        .as("테스트 회원은 받지 않음 (본인 제보의 답장)")
        .containsExactly(reporter);
    JsonNode request = onlyRequest();
    assertThat(request.path("type").asString()).isEqualTo("REPORT_ANSWERED");
    assertThat(request.path("title").asString()).isEqualTo("제보 답변: 서초구 서리풀 청년아트타운 잔여세대 입주자 모집공고");
    assertThat(request.path("body").asString()).isEqualTo("제보하신 '보증금' 내용을 확인하고 고쳤어요.");
    assertThat(request.path("recipients")).hasSize(1);
    assertThat(request.toString()).doesNotContain("2,600만 원으로 고쳤어요");
  }

  @Test
  void reportResolvedWithoutAReplyIsNotAlerted() throws Exception {
    UUID notice = seoripul();
    UUID reporter = member();
    subscribe(reporter);
    UUID report = reports.report(notice, deposit(), reporter.toString()).id();
    jdbc.sql("delete from common.outbox").update();

    reports.resolve(report, new AdminReportResolveRequest(Result.KEPT, null, null), "admin-1");

    assertThat(requests()).isEmpty();
    assertThat(
            jdbc.sql(
                    "select count(*) from notification.notifications where type = 'REPORT_ANSWERED'")
                .query(Long.class)
                .single())
        .isZero();
  }

  private UUID seoripul() throws Exception {
    try (InputStream in =
        getClass().getResourceAsStream("/notice/extraction-completed-seoripul.json")) {
      ingestion.apply(new String(in.readAllBytes(), StandardCharsets.UTF_8));
    }
    return jdbc.sql("select id from notice.notices").query(UUID.class).single();
  }

  private static NoticeReportRequest deposit() {
    return new NoticeReportRequest("보증금", "2,400만 원", "2,600만 원", "정정 공고 확인", "공고 상세");
  }

  private UUID member() {
    return logins
        .login(new SocialProfile(SocialProvider.KAKAO, "reporter-" + UUID.randomUUID(), "닉네임"))
        .userId();
  }

  private void subscribe(UUID userId) {
    jdbc.sql(
            """
            insert into notification.push_subscriptions
                (id, user_id, endpoint, p256dh, auth, created_at, updated_at)
            values (:id, :userId, :endpoint, 'p256dh', 'auth', now(), now())
            """)
        .param("id", UUID.randomUUID())
        .param("userId", userId)
        .param("endpoint", "https://fcm.googleapis.com/fcm/send/" + userId)
        .update();
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
