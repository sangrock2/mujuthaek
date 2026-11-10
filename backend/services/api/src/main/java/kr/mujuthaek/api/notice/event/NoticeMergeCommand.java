package kr.mujuthaek.api.notice.event;

import java.util.UUID;
import kr.mujuthaek.api.notice.repository.NoticeRepository.DuplicateCandidate;
import kr.mujuthaek.api.notice.service.internal.NoticeIngestionService;
import kr.mujuthaek.api.notice.service.internal.NoticeMergeService;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

/**
 * 같은 공고 후보 확인·합치기 명령. 실행하면 작업하고 바로 끝나요(서버로 뜨지 않음). 관리자 화면이 생기기 전까지 운영자가 써요.
 *
 * <pre>
 * 후보 보기   --notice.merge=list
 * 다시 훑기   --notice.merge=scan (이미 공개된 공고끼리 같은 공고를 찾아 자동으로 합침)
 * 합치기      --notice.merge=merge --notice.merge.from=나중_공고ID --notice.merge.into=남길_공고ID
 * 아니라고 표시 --notice.merge=reject --notice.merge.from=공고ID --notice.merge.into=후보_공고ID
 * 합치기 되돌리기 --notice.merge=unmerge --notice.merge.from=합쳐진_공고ID (같은 공고로 잘못 자동 합쳐졌을 때)
 * (함께: --spring.main.web-application-type=none --spring.rabbitmq.listener.simple.auto-startup=false)
 * </pre>
 */
@Component
@ConditionalOnProperty(name = "notice.merge")
class NoticeMergeCommand implements ApplicationRunner {

  private final NoticeMergeService merges;
  private final NoticeIngestionService ingestion;
  private final ConfigurableApplicationContext context;
  private final Environment env;

  NoticeMergeCommand(
      NoticeMergeService merges,
      NoticeIngestionService ingestion,
      ConfigurableApplicationContext context,
      Environment env) {
    this.merges = merges;
    this.ingestion = ingestion;
    this.context = context;
    this.env = env;
  }

  @Override
  public void run(ApplicationArguments args) {
    int exit = 0;
    try {
      System.out.println(execute(env.getRequiredProperty("notice.merge")));
    } catch (IllegalArgumentException | IllegalStateException e) {
      System.out.println("실패: " + e.getMessage());
      exit = 1;
    }
    int code = exit;
    System.exit(SpringApplication.exit(context, () -> code));
  }

  String execute(String action) {
    return switch (action) {
      case "list" -> list();
      case "merge" -> {
        ingestion.merge(id("notice.merge.from"), id("notice.merge.into"));
        yield "합쳤어요";
      }
      case "scan" -> "같은 공고로 판정돼 합친 공고 " + ingestion.mergeDuplicates() + "건";
      case "unmerge" -> {
        ingestion.unmerge(id("notice.merge.from"));
        yield "합치기를 되돌렸어요";
      }
      case "reject" ->
          merges.reject(id("notice.merge.from"), id("notice.merge.into"))
              ? "같은 공고가 아니라고 표시했어요"
              : "대기 중인 후보가 없어요";
      default ->
          throw new IllegalArgumentException(
              "list, scan, merge, unmerge, reject 중 하나여야 해요: " + action);
    };
  }

  private String list() {
    StringBuilder out = new StringBuilder();
    for (DuplicateCandidate c : merges.pendingCandidates()) {
      out.append(c.noticeId())
          .append(" (")
          .append(c.noticeTitle())
          .append(") -> ")
          .append(c.candidateOf())
          .append(" (")
          .append(c.candidateTitle())
          .append(") ")
          .append(c.reason())
          .append('\n');
    }
    return out.isEmpty() ? "확인할 후보가 없어요" : out.toString().strip();
  }

  private UUID id(String property) {
    try {
      return UUID.fromString(env.getRequiredProperty(property));
    } catch (IllegalArgumentException e) {
      throw new IllegalArgumentException(property + " 값이 공고 ID가 아니에요");
    }
  }
}
