package kr.mujuthaek.api.notice.event;

import java.util.EnumSet;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import kr.mujuthaek.api.notice.service.internal.NoticeBackfillService;
import kr.mujuthaek.api.notice.service.internal.NoticeBackfillService.Kind;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

/**
 * 보충 발행 명령. 받는 모듈의 리스너가 같은 프로세스 안에서 처리하므로, 받는 쪽이 비동기(@Async)면 끝날 때까지 기다리도록 종료 대기 옵션을 함께 줘요.
 *
 * <pre>
 * ./gradlew bootRun --args='--notice.backfill=published,locations
 *     [--notice.backfill.include-closed=true]
 *     --spring.main.web-application-type=none --spring.rabbitmq.listener.simple.auto-startup=false
 *     --notice.status-refresh.enabled=false
 *     --spring.task.execution.shutdown.await-termination=true
 *     --spring.task.execution.shutdown.await-termination-period=5m'
 * </pre>
 */
@Component
@ConditionalOnProperty(name = "notice.backfill")
class NoticeBackfillCommand implements ApplicationRunner {

  private final NoticeBackfillService backfill;
  private final ConfigurableApplicationContext context;
  private final Environment env;

  NoticeBackfillCommand(
      NoticeBackfillService backfill, ConfigurableApplicationContext context, Environment env) {
    this.backfill = backfill;
    this.context = context;
    this.env = env;
  }

  @Override
  public void run(ApplicationArguments args) {
    int exit = 0;
    try {
      Map<Kind, Integer> sent =
          backfill.republish(
              kinds(env.getRequiredProperty("notice.backfill")),
              env.getProperty("notice.backfill.include-closed", Boolean.class, false));
      System.out.println("보충 발행: " + sent);
    } catch (IllegalArgumentException e) {
      System.out.println("실패: " + e.getMessage());
      exit = 1;
    }
    int code = exit;
    System.exit(SpringApplication.exit(context, () -> code));
  }

  /** "published,locations" → {PUBLISHED, LOCATIONS}. */
  static Set<Kind> kinds(String value) {
    Set<Kind> kinds = EnumSet.noneOf(Kind.class);
    for (String part : value.split(",")) {
      String name = part.strip().toUpperCase(Locale.ROOT);
      if (name.isEmpty()) {
        continue;
      }
      try {
        kinds.add(Kind.valueOf(name));
      } catch (IllegalArgumentException e) {
        throw new IllegalArgumentException("published, locations 중에서 골라야 해요: " + part.strip());
      }
    }
    if (kinds.isEmpty()) {
      throw new IllegalArgumentException("보낼 이벤트를 하나 이상 골라야 해요 (published, locations)");
    }
    return kinds;
  }
}
