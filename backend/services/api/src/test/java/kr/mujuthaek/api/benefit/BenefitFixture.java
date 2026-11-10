package kr.mujuthaek.api.benefit;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.time.Clock;
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.function.Consumer;
import kr.mujuthaek.api.TestDatabase;
import kr.mujuthaek.api.benefit.repository.BenefitRepository;
import kr.mujuthaek.api.benefit.service.BenefitQueryService;
import kr.mujuthaek.api.benefit.service.internal.BenefitDetailService;
import kr.mujuthaek.api.benefit.service.internal.BenefitIngestionService;
import kr.mujuthaek.api.benefit.service.internal.BenefitStatusService;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.simple.JdbcClient;
import tools.jackson.databind.json.JsonMapper;
import tools.jackson.databind.node.ObjectNode;

/** 혜택 테스트 공통: 테스트 DB, 오늘 2026-10-22 고정, 계약 예시(policy.extracted.json)로 만든 이벤트. */
public class BenefitFixture {

  public static final LocalDate TODAY = LocalDate.of(2026, 10, 22);
  public static final JsonMapper JSON = JsonMapper.builder().build();

  public final JdbcTemplate jdbc = new JdbcTemplate(TestDatabase.dataSource());
  public final Clock clock =
      Clock.fixed(TODAY.atStartOfDay(ZoneId.of("Asia/Seoul")).toInstant(), ZoneId.of("Asia/Seoul"));
  public final List<Object> published = new ArrayList<>();
  public final BenefitRepository repository = new BenefitRepository(JdbcClient.create(jdbc));
  public final BenefitIngestionService ingest =
      new BenefitIngestionService(repository, published::add, JSON, clock);
  public final BenefitStatusService status =
      new BenefitStatusService(repository, published::add, clock);
  public final BenefitQueryService queries = new BenefitQueryService(repository);
  public final BenefitDetailService details = new BenefitDetailService(repository, clock);

  /** 예시 봉투를 이 정책 ID·버전으로 바꾸고 change로 payload를 고쳐요. eventId는 새로. */
  public static String event(UUID rawPolicyId, int version, Consumer<ObjectNode> change) {
    ObjectNode envelope = (ObjectNode) JSON.readTree(example());
    envelope.put("eventId", UUID.randomUUID().toString());
    ObjectNode p = (ObjectNode) envelope.get("payload");
    p.put("rawPolicyId", rawPolicyId.toString());
    p.put("version", version);
    p.put("policyId", "policy-" + rawPolicyId);
    // 예시는 신청 마감이 지난 정책이라, 기본은 오늘 접수 중으로 바꿔요
    ObjectNode schedule = (ObjectNode) p.get("schedule");
    schedule.put("applyStart", "2026-10-01").put("applyEnd", "2026-11-30");
    change.accept(p);
    return JSON.writeValueAsString(envelope);
  }

  /** 새 정책을 저장하고 혜택 ID를 돌려줘요. */
  public UUID benefit(Consumer<ObjectNode> change) {
    UUID raw = UUID.randomUUID();
    ingest.apply(event(raw, 1, change));
    return repository.findByRawPolicyId(raw).orElseThrow().id();
  }

  private static String example() {
    try (InputStream in =
        BenefitFixture.class.getResourceAsStream("/contracts/examples/policy.extracted.json")) {
      return new String(in.readAllBytes(), StandardCharsets.UTF_8);
    } catch (IOException e) {
      throw new IllegalStateException(e);
    }
  }
}
