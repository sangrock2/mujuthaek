package kr.mujuthaek.api.notification;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import java.util.UUID;
import kr.mujuthaek.api.TestcontainersConfiguration;
import kr.mujuthaek.api.benefit.BenefitFixture;
import kr.mujuthaek.api.benefit.service.internal.BenefitIngestionService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.simple.JdbcClient;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;
import tools.jackson.databind.node.ObjectNode;

/** benefit 내부 이벤트 → notification.requested (아웃박스에 같은 트랜잭션으로). */
@SpringBootTest(
    properties = {
      "app.outbox.scheduling-enabled=false",
      "app.notification.test-recipients[0].user-id=0192b6f0-0000-7000-8000-0000000000a1",
      "app.notification.test-recipients[0].email=me@example.com",
      "app.notification.test-recipients[0].quiet-enabled=false"
    })
@Import({TestcontainersConfiguration.class, NotificationTestClock.class})
class BenefitNotificationRequestTest {

  @Autowired BenefitIngestionService ingestion;
  @Autowired JdbcClient jdbc;
  @Autowired JsonMapper json;

  @BeforeEach
  void clear() {
    jdbc.sql("delete from benefit.benefits").update();
    jdbc.sql("delete from common.outbox").update();
  }

  @Test
  void newPolicyBecomesNewSupportRequest() {
    ingestion.apply(BenefitFixture.event(UUID.randomUUID(), 1, p -> {}));

    JsonNode p = onlyRequest();
    assertThat(p.path("type").asString()).isEqualTo("NEW_SUPPORT");
    assertThat(p.path("target").path("type").asString()).isEqualTo("BENEFIT");
    String id = p.path("target").path("id").asString();
    assertThat(p.path("dedupKey").asString()).isEqualTo("BENEFIT:" + id + ":NEW");
    assertThat(p.path("linkPath").asString()).isEqualTo("/benefits/" + id);
    assertThat(p.path("title").asString()).isEqualTo("새 지원 정책: 청년 취업자 주거비 지원사업");
    assertThat(p.path("body").asString())
        .isEqualTo("관심 조건에 맞는 새 지원 정책 소식이에요. 전북특별자치도 무주군 · 11월 30일 마감");
    assertThat(p.path("recipients").get(0).path("email").asString()).isEqualTo("me@example.com");
  }

  @Test
  void changedScheduleBecomesCorrectedRequest() {
    UUID raw = UUID.randomUUID();
    ingestion.apply(BenefitFixture.event(raw, 1, p -> {}));
    jdbc.sql("delete from common.outbox").update();

    ingestion.apply(
        BenefitFixture.event(
            raw,
            2,
            p -> {
              p.withObject("schedule").put("applyEnd", "2026-12-15");
              ((ObjectNode) p.withArray("conditions").get(0)).withObject("value").put("max", 34);
            }));

    JsonNode p = onlyRequest();
    assertThat(p.path("type").asString()).isEqualTo("CORRECTED");
    assertThat(p.path("dedupKey").asString()).endsWith(":CORRECTED:2");
    assertThat(p.path("body").asString()).isEqualTo("관심 지원 정책의 일정, 자격 내용이 바뀌었어요.");
  }

  @Test
  void titleOnlyChangeIsNotAlerted() {
    UUID raw = UUID.randomUUID();
    ingestion.apply(BenefitFixture.event(raw, 1, p -> {}));
    jdbc.sql("delete from common.outbox").update();

    ingestion.apply(
        BenefitFixture.event(
            raw, 2, p -> p.withObject("source").put("title", "청년 취업자 주거비 지원사업 (2차)")));

    assertThat(requests()).isEmpty(); // basic은 BenefitUpdated에는 있지만 알리지 않아요
  }

  @Test
  void reprocessAndClosedAreNotAlerted() {
    ingestion.apply(BenefitFixture.event(UUID.randomUUID(), 1, p -> p.put("reprocess", true)));
    ingestion.apply(
        BenefitFixture.event(
            UUID.randomUUID(),
            1,
            p -> {
              p.withObject("schedule")
                  .put("applyStart", "2025-01-01")
                  .put("applyEnd", "2025-02-01");
              p.withObject("source").put("title", "작년 정책");
            }));

    assertThat(requests()).isEmpty();
  }

  private JsonNode onlyRequest() {
    List<JsonNode> found = requests();
    assertThat(found).hasSize(1);
    return found.getFirst();
  }

  private List<JsonNode> requests() {
    return jdbc
        .sql(
            "select payload::text from common.outbox where event_type = 'notification.requested' order by created_at")
        .query(String.class)
        .list()
        .stream()
        .map(s -> json.readTree(s).path("payload"))
        .toList();
  }
}
