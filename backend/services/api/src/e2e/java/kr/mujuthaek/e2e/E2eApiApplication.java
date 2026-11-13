package kr.mujuthaek.e2e;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneId;
import java.util.Map;
import java.util.UUID;
import kr.mujuthaek.api.ApiApplication;
import kr.mujuthaek.api.notice.mapper.NoticeProjection;
import kr.mujuthaek.api.notice.service.internal.NoticeIngestionService;
import kr.mujuthaek.api.notification.service.internal.DeadlineReminderService;
import kr.mujuthaek.api.user.domain.SocialProvider;
import kr.mujuthaek.api.user.security.RefreshTokenCookies;
import kr.mujuthaek.api.user.service.AuthTokenService;
import kr.mujuthaek.api.user.service.SocialLoginService;
import kr.mujuthaek.api.user.service.SocialProfile;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.filter.OncePerRequestFilter;
import org.springframework.web.server.ResponseStatusException;
import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.CreateBucketRequest;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;
import tools.jackson.databind.json.JsonMapper;
import tools.jackson.databind.node.ArrayNode;
import tools.jackson.databind.node.ObjectNode;

/** 별도 소스 세트에서만 실행하는 loopback 전용 서버. 운영 jar에 포함되지 않는다. */
public class E2eApiApplication {
  public static void main(String[] args) {
    if (!"1".equals(System.getenv("E2E_ALLOW_LOCAL")) || System.getenv("E2E_CONTROL_KEY") == null)
      throw new IllegalStateException("E2E 전용 실행 도구로 시작하세요");
    new SpringApplicationBuilder(ApiApplication.class, Support.class).profiles("e2e").run(args);
  }

  @Configuration(proxyBeanMethods = false)
  static class Support {
    @Bean
    @Primary
    Clock e2eClock() {
      return Clock.fixed(Instant.parse("2026-11-12T02:05:00Z"), ZoneId.of("Asia/Seoul"));
    }

    @Bean
    Control control(
        JdbcClient jdbc,
        JsonMapper json,
        NoticeIngestionService ingestion,
        SocialLoginService login,
        AuthTokenService tokens,
        RefreshTokenCookies cookies,
        DeadlineReminderService reminders,
        S3Client s3) {
      return new Control(jdbc, json, ingestion, login, tokens, cookies, reminders, s3);
    }

    @Bean
    OncePerRequestFilter e2eKey() {
      return new OncePerRequestFilter() {
        @Override
        protected void doFilterInternal(
            HttpServletRequest request, HttpServletResponse response, FilterChain chain)
            throws ServletException, IOException {
          if (request.getRequestURI().startsWith("/_e2e/")
              && !MessageDigest.isEqual(
                  System.getenv("E2E_CONTROL_KEY").getBytes(StandardCharsets.UTF_8),
                  String.valueOf(request.getHeader("X-E2E-Key"))
                      .getBytes(StandardCharsets.UTF_8))) {
            response.sendError(403);
            return;
          }
          chain.doFilter(request, response);
        }
      };
    }
  }

  @RestController
  @RequestMapping("/_e2e")
  static class Control {
    private final JdbcClient jdbc;
    private final JsonMapper json;
    private final NoticeIngestionService ingestion;
    private final SocialLoginService login;
    private final AuthTokenService tokens;
    private final RefreshTokenCookies cookies;
    private final DeadlineReminderService reminders;
    private final S3Client s3;
    private UUID noticeId;
    private ObjectNode original;

    Control(
        JdbcClient jdbc,
        JsonMapper json,
        NoticeIngestionService ingestion,
        SocialLoginService login,
        AuthTokenService tokens,
        RefreshTokenCookies cookies,
        DeadlineReminderService reminders,
        S3Client s3) {
      this.jdbc = jdbc;
      this.json = json;
      this.ingestion = ingestion;
      this.login = login;
      this.tokens = tokens;
      this.cookies = cookies;
      this.reminders = reminders;
      this.s3 = s3;
    }

    @PostMapping("/reset")
    synchronized Map<String, Object> reset() throws Exception {
      jdbc.sql(
              "truncate account.users,notice.notices,notice.extraction_results,common.processed_events,common.outbox,notification.notifications,notification.reminder_runs,notification.push_subscriptions cascade")
          .update();
      try (var in =
          getClass().getResourceAsStream("/contracts/examples/extraction.completed.json")) {
        original =
            (ObjectNode) json.readTree(new String(in.readAllBytes(), StandardCharsets.UTF_8));
      }
      var payload = (ObjectNode) original.path("payload");
      var detail = (ObjectNode) payload.path("notice");
      payload.put("title", "E2E 청년 주거 신청 공고");
      ((ObjectNode) detail.path("notice")).put("title", "E2E 청년 주거 신청 공고");
      while (detail.path("eligibility").size() > 1)
        ((ArrayNode) detail.path("eligibility")).remove(1);
      while (payload.path("conditions").size() > 1)
        ((ArrayNode) payload.path("conditions")).remove(1);
      var frame = payload.putObject("judgment");
      frame.put("schema", "housing-judgment.v1").set("rawPostId", payload.path("rawPostId"));
      frame.put("rawVersion", 1).put("referenceDate", "2026-10-01");
      frame
          .putArray("common")
          .addObject()
          .put("id", "e2e-age")
          .put("kind", "AGE")
          .put("quote", "공고일 만 19세 이상 39세 이하")
          .put("page", 1)
          .put("inReview", false)
          .putNull("reviewReason")
          .put("minAge", 19)
          .put("maxAge", 39);
      frame
          .putArray("groups")
          .addObject()
          .put("id", "youth")
          .put("name", "청년")
          .putArray("criteria");
      frame.putArray("notes");
      ((ObjectNode) detail.path("requiredDocuments").get(0))
          .put("group", "COMMON")
          .put("appliesTo", "신청자");
      var schedule = (ObjectNode) detail.path("schedules").get(0);
      ((ObjectNode) schedule.path("startsAt")).put("value", "2026-11-01T10:00:00+09:00");
      ((ObjectNode) schedule.path("endsAt")).put("value", "2026-11-15T17:00:00+09:00");
      // 목록용 일정도 실제 문서와 동일하게 고정한다.
      var summary = (ObjectNode) payload.path("schedule");
      summary.put("applyStartOn", "2026-11-01");
      summary.put("applyEndOn", "2026-11-15");
      for (var window : payload.path("applicationWindows")) {
        ((ObjectNode) window).put("applyStartOn", "2026-11-01").put("applyEndOn", "2026-11-15");
      }
      byte[] pdf = samplePdf();
      try {
        s3.createBucket(CreateBucketRequest.builder().bucket("e2e-raw").build());
      } catch (software.amazon.awssdk.services.s3.model.S3Exception e) {
        if (e.statusCode() != 409) throw e;
      }
      s3.putObject(
          PutObjectRequest.builder()
              .bucket("e2e-raw")
              .key("raw/e2e/notice.pdf")
              .contentType("application/pdf")
              .build(),
          RequestBody.fromBytes(pdf));
      var document = ((ArrayNode) detail.path("documents")).addObject();
      document
          .put("id", "pdf1")
          .put("kind", "PDF")
          .put("name", "신청 준비 테스트 원문.pdf")
          .put(
              "sha256",
              java.util.HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(pdf)))
          .putNull("originalUrl")
          .put("pageCount", 1);
      payload
          .putArray("sourceFiles")
          .addObject()
          .put("documentId", "pdf1")
          .put("s3Key", "raw/e2e/notice.pdf");
      var evidence = (ObjectNode) detail.path("evidence").get(0);
      evidence.put("sourceId", "pdf1").put("quote", "Applicants must be 19 to 39 years old.");
      evidence.putObject("locator").put("kind", "PDF_PAGE").put("page", 1).putNull("printedPage");
      payload.set("schedule", NoticeProjection.schedule(detail, true));
      payload.set("applicationWindows", NoticeProjection.windows(detail, true));
      String result = ingestion.apply(original.toString()).name();
      if (!"PUBLISHED".equals(result)) throw new IllegalStateException(result);
      noticeId =
          jdbc.sql("select id from notice.notices where not hidden and merged_into is null")
              .query(UUID.class)
              .single();
      var one = login.login(new SocialProfile(SocialProvider.KAKAO, "e2e-u1", "E2E 준비 회원"));
      var two = login.login(new SocialProfile(SocialProvider.KAKAO, "e2e-u2", "E2E 다른 회원"));
      jdbc.sql(
              "insert into notification.push_subscriptions(id,user_id,endpoint,p256dh,auth,created_at,updated_at) values(:id,:user,'https://fcm.googleapis.com/e2e','e2e-test-public-key','e2e-test-auth',now(),now())")
          .param("id", UUID.randomUUID())
          .param("user", one.userId())
          .update();
      return Map.of("noticeId", noticeId, "user1", one.userId(), "user2", two.userId());
    }

    @PostMapping("/session/{account}")
    void session(@PathVariable String account, HttpServletResponse response) {
      if (!account.equals("u1") && !account.equals("u2"))
        throw new ResponseStatusException(HttpStatus.BAD_REQUEST);
      var user =
          login.login(new SocialProfile(SocialProvider.KAKAO, "e2e-" + account, "E2E " + account));
      var pair = tokens.issue(user);
      cookies.write(response, pair.refreshToken(), pair.refreshTokenTtl());
    }

    // ASCII 한 쪽 PDF. 테스트 근거 문장과 실제 PDF 텍스트가 동일하다.
    private byte[] samplePdf() {
      String text =
          "BT /F1 14 Tf 72 720 Td (Applicants must be 19 to 39 years old.) Tj 0 -30 Td (Resident certificate required.) Tj ET\n";
      String[] objects = {
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        "<< /Length " + text.length() + " >>\nstream\n" + text + "endstream"
      };
      StringBuilder body = new StringBuilder("%PDF-1.4\n");
      int[] offsets = new int[6];
      for (int i = 0; i < objects.length; i++) {
        offsets[i + 1] = body.length();
        body.append(i + 1).append(" 0 obj\n").append(objects[i]).append("\nendobj\n");
      }
      int xref = body.length();
      body.append("xref\n0 6\n0000000000 65535 f \n");
      for (int i = 1; i < 6; i++)
        body.append(String.format(java.util.Locale.ROOT, "%010d 00000 n \n", offsets[i]));
      body.append("trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n")
          .append(xref)
          .append("\n%%EOF\n");
      return body.toString().getBytes(StandardCharsets.US_ASCII);
    }

    @PostMapping("/reminders")
    Map<String, Object> reminders() {
      return Map.of("requested", reminders.runIfDue().orElse(0));
    }

    @PostMapping("/correction")
    void correction() {
      original.put("eventId", UUID.randomUUID().toString());
      ((ObjectNode) original.path("payload")).put("rawVersion", 2);
      ((ObjectNode) original.path("payload").path("judgment")).put("rawVersion", 2);
      ((ObjectNode) original.path("payload").path("notice").path("input")).put("rawVersion", 2);
      ((ObjectNode) original.path("payload").path("notice").path("sourceReferences").get(0))
          .put("rawVersion", 2);
      ((ObjectNode) original.path("payload").path("notice").path("requiredDocuments").get(0))
          .put("name", "정정된 주민등록표등본");
      ingestion.apply(original.toString());
      ingestion.apply(original.toString());
    }

    @GetMapping("/state")
    Map<String, Object> state() {
      return Map.of(
          "pendingOutbox",
          jdbc.sql("select count(*) from common.outbox where published_at is null")
              .query(Long.class)
              .single());
    }
  }
}
