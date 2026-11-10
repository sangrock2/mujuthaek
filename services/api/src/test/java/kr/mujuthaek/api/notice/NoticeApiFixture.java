package kr.mujuthaek.api.notice;

import java.time.Clock;
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.UUID;
import kr.mujuthaek.api.TestDatabase;
import kr.mujuthaek.api.area.repository.PostgresLocationScores;
import kr.mujuthaek.api.area.repository.PostgresNoticeLocations;
import kr.mujuthaek.api.area.repository.PostgresSiteDetails;
import kr.mujuthaek.api.area.service.NoticeAreaQueryService;
import kr.mujuthaek.api.common.exception.GlobalExceptionHandlerAccess;
import kr.mujuthaek.api.common.region.RegionQueryService;
import kr.mujuthaek.api.notice.repository.AreaScoreRepository;
import kr.mujuthaek.api.notice.repository.ExtractionResultRepository;
import kr.mujuthaek.api.notice.repository.FollowUpRepository;
import kr.mujuthaek.api.notice.repository.NoticeQueries;
import kr.mujuthaek.api.notice.repository.NoticeRepository;
import kr.mujuthaek.api.notice.repository.PolicyDuplicateRepository;
import kr.mujuthaek.api.notice.service.NoticeQueryService;
import kr.mujuthaek.api.notice.service.internal.NoticeIngestionService;
import kr.mujuthaek.api.notice.service.internal.NoticeMergeService;
import kr.mujuthaek.api.notice.service.internal.PolicyDuplicateService;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import tools.jackson.databind.node.ObjectNode;

/** 공고 API 테스트: 실제 DB에 공고를 저장하고, 오늘을 2026-10-22로 고정한 MockMvc로 불러요. */
public class NoticeApiFixture {

  public static final LocalDate TODAY = LocalDate.of(2026, 10, 22);

  public final JdbcTemplate jdbc = new JdbcTemplate(TestDatabase.dataSource());
  private final JdbcClient client = JdbcClient.create(jdbc);
  private final Clock clock =
      Clock.fixed(TODAY.atStartOfDay(ZoneId.of("Asia/Seoul")).toInstant(), ZoneId.of("Asia/Seoul"));
  private final NoticeRepository notices = new NoticeRepository(client);
  private final FollowUpRepository followUps = new FollowUpRepository(client);
  public final NoticeIngestionService ingest =
      new NoticeIngestionService(
          notices,
          new ExtractionResultRepository(client),
          followUps,
          new NoticeMergeService(notices, followUps, event -> {}, clock),
          new PolicyDuplicateService(new PolicyDuplicateRepository(client), clock, event -> {}),
          event -> {},
          NoticeFixtures.JSON,
          clock);
  public final NoticeQueryService queries =
      new NoticeQueryService(
          new NoticeQueries(jdbc),
          new FollowUpRepository(client),
          new AreaScoreRepository(client),
          new RegionQueryService(jdbc),
          new NoticeAreaQueryService(
              new PostgresNoticeLocations(TestDatabase.dataSource()),
              new PostgresSiteDetails(TestDatabase.dataSource()),
              new PostgresLocationScores(TestDatabase.dataSource())),
          clock,
          NoticeFixtures.JSON);

  /** 테스트마다 다른 기관 이름이라, providers 필터로 이 테스트의 공고만 봐요. */
  public final String provider = "T" + UUID.randomUUID().toString().substring(0, 8);

  private int count;

  public MockMvc mvc(Object... controllers) {
    return MockMvcBuilders.standaloneSetup(controllers)
        .setControllerAdvice(GlobalExceptionHandlerAccess.handler())
        .build();
  }

  /**
   * 공고 하나를 받아 반영하고 공고 ID를 돌려줘요. edit로 payload를 바꿔요. 공개되지 않은 결과(검수 대기 등)는 공고가 생기지 않아 아무 공고도 아닌 새 ID를
   * 돌려줘요.
   */
  public UUID notice(java.util.function.Consumer<ObjectNode> edit) {
    UUID raw = UUID.randomUUID();
    ObjectNode p = NoticeFixtures.payload(raw, 1);
    p.put("provider", provider);
    // 같은 내용의 공고를 여러 개 만들어도 같은 공고로 합쳐지지 않게 공급 기관을 공고마다 달리 해요
    ((ObjectNode) p.get("notice").get("notice")).put("publisher", provider + "-" + ++count);
    edit.accept(p);
    receive(p);
    return jdbc
        .queryForList("select id from notice.notices where raw_post_id = ?", UUID.class, raw)
        .stream()
        .findFirst()
        .orElseGet(UUID::randomUUID);
  }

  /** payload 하나를 extraction.completed로 받아요. */
  public void receive(ObjectNode payload) {
    ingest.apply(NoticeFixtures.envelope(payload));
  }

  public static void schedule(ObjectNode p, String start, String end) {
    NoticeFixtures.schedule(p, start, end);
  }
}
