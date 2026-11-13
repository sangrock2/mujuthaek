package kr.mujuthaek.e2e;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneId;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import kr.mujuthaek.notification.NotificationApplication;
import kr.mujuthaek.notification.delivery.email.EmailSender;
import kr.mujuthaek.notification.delivery.push.PushResponse;
import kr.mujuthaek.notification.delivery.push.PushSender;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

/** 외부 발송만 기록기로 대체. 수신·중복 방지·DB·채널·워커는 실제 구현을 사용한다. */
public class E2eNotificationApplication {
  public static void main(String[] args) {
    if (!"1".equals(System.getenv("E2E_ALLOW_LOCAL")) || System.getenv("E2E_CONTROL_KEY") == null)
      throw new IllegalStateException("E2E 전용 실행 도구로 시작하세요");
    new SpringApplicationBuilder(NotificationApplication.class, Support.class)
        .profiles("e2e")
        .run(args);
  }

  @Configuration(proxyBeanMethods = false)
  static class Support {
    @Bean
    @Primary
    Clock e2eClock() {
      return Clock.fixed(Instant.parse("2026-11-12T02:05:00Z"), ZoneId.of("Asia/Seoul"));
    }

    @Bean
    Recorder recorder() {
      return new Recorder();
    }

    @Bean
    @Primary
    EmailSender recordingEmail(Recorder recorder) {
      return message -> {
        recorder.subjects.add(message.subject());
        return "e2e-recorded";
      };
    }

    @Bean
    @Primary
    PushSender recordingPush(Recorder recorder) {
      return message -> {
        recorder.subjects.add(
            new String(message.payload(), java.nio.charset.StandardCharsets.UTF_8));
        return new PushResponse(201, null);
      };
    }
  }

  @RestController
  static class Recorder {
    final CopyOnWriteArrayList<String> subjects = new CopyOnWriteArrayList<>();

    @GetMapping("/_e2e/sent")
    List<String> sent(@RequestHeader("X-E2E-Key") String key) {
      if (!System.getenv("E2E_CONTROL_KEY").equals(key))
        throw new ResponseStatusException(HttpStatus.FORBIDDEN);
      return List.copyOf(subjects);
    }
  }
}
