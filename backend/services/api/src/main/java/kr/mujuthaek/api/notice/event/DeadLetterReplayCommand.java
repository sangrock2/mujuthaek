package kr.mujuthaek.api.notice.event;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.stereotype.Component;

/**
 * 실패 큐 다시 넣기 명령. api를 이 옵션으로 실행하면 다시 넣고 바로 끝나요(서버로 뜨지 않음).
 *
 * <pre>
 * ./gradlew bootRun --args='--notice.dead-letter.replay=100 --spring.main.web-application-type=none
 *     --spring.rabbitmq.listener.simple.auto-startup=false'
 * </pre>
 */
@Component
@ConditionalOnProperty(name = "notice.dead-letter.replay")
class DeadLetterReplayCommand implements ApplicationRunner {

  private final DeadLetterReplayer replayer;
  private final ConfigurableApplicationContext context;
  private final int limit;

  DeadLetterReplayCommand(
      DeadLetterReplayer replayer,
      ConfigurableApplicationContext context,
      org.springframework.core.env.Environment env) {
    this.replayer = replayer;
    this.context = context;
    this.limit = env.getRequiredProperty("notice.dead-letter.replay", Integer.class);
  }

  @Override
  public void run(ApplicationArguments args) {
    DeadLetterReplayer.Result result = replayer.replay(limit);
    System.out.printf("원래 큐로 %d건, 횟수 초과로 남김 %d건%n", result.replayed(), result.parked());
    System.exit(SpringApplication.exit(context, () -> 0));
  }
}
