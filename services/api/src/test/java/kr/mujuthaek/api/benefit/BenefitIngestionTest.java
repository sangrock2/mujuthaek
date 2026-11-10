package kr.mujuthaek.api.benefit;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.List;
import java.util.UUID;
import kr.mujuthaek.api.benefit.mapper.PolicyExtractedEvent;
import kr.mujuthaek.api.common.event.BenefitClosed;
import kr.mujuthaek.api.common.event.BenefitPublished;
import kr.mujuthaek.api.common.event.BenefitUpdated;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.node.ObjectNode;

/** 정책 추출 결과 저장 규칙 (policy-extracted.draft.md 4장). */
class BenefitIngestionTest {

  private final BenefitFixture f = new BenefitFixture();

  private int count(String table, UUID benefitId) {
    return f.jdbc.queryForObject(
        "select count(*) from benefit." + table + " where benefit_id = ?",
        Integer.class,
        benefitId);
  }

  @Test
  void 처음_받은_정책은_한_줄과_지원_조건_줄로_저장하고_알린다() {
    UUID raw = UUID.randomUUID();
    f.ingest.apply(BenefitFixture.event(raw, 1, p -> {}));

    UUID id = f.repository.findByRawPolicyId(raw).orElseThrow().id();
    var row =
        f.jdbc.queryForMap(
            "select status, category, region_codes::text as regions, title from benefit.benefits"
                + " where id = ?",
            id);
    assertThat(row.get("status")).isEqualTo("OPEN");
    assertThat(row.get("category")).isEqualTo("HOUSING");
    assertThat(row.get("regions")).isEqualTo("{52730}");
    assertThat(count("benefit_supports", id)).isEqualTo(1);
    assertThat(count("benefit_conditions", id)).isEqualTo(9);
    assertThat(f.published)
        .singleElement()
        .isInstanceOfSatisfying(
            BenefitPublished.class,
            e -> {
              assertThat(e.regionScope()).isEqualTo("SIGUNGU");
              assertThat(e.regionCodes()).containsExactly("52730");
              assertThat(e.field()).isEqualTo("BENEFIT");
              assertThat(e.reprocess()).isFalse();
            });
  }

  @Test
  void 여러_지역_정책은_지역을_모두_담아_알린다() {
    f.benefit(
        p -> {
          var source = p.withObject("source");
          source.put("regionScope", "SIDO");
          source.putArray("regionCodes").add("11").add("41");
        });

    assertThat(f.published)
        .singleElement()
        .isInstanceOfSatisfying(
            BenefitPublished.class,
            e -> {
              assertThat(e.regionScope()).isEqualTo("SIDO");
              assertThat(e.regionCodes()).containsExactly("11", "41");
            });
  }

  @Test
  void 숨겨져_있다가_새_버전에서_보이면_새_혜택으로_알린다() {
    UUID raw = UUID.randomUUID();
    f.ingest.apply(BenefitFixture.event(raw, 1, p -> p.put("relevant", false)));
    assertThat(f.published).isEmpty();

    f.ingest.apply(BenefitFixture.event(raw, 2, p -> {}));

    assertThat(f.published).singleElement().isInstanceOf(BenefitPublished.class);
  }

  @Test
  void 보이던_혜택의_구조_값이_바뀌면_바뀐_부분을_알린다() {
    UUID raw = UUID.randomUUID();
    f.ingest.apply(BenefitFixture.event(raw, 1, p -> {}));
    UUID id = f.repository.findByRawPolicyId(raw).orElseThrow().id();
    f.published.clear();

    f.ingest.apply(
        BenefitFixture.event(
            raw,
            2,
            p -> {
              p.withObject("schedule").put("applyEnd", "2026-12-15");
              ((ObjectNode) p.withArray("supports").get(0)).put("amountMax", 30);
              ((ObjectNode) p.withArray("conditions").get(0)).withObject("value").put("max", 45);
              p.putArray("documents").add("주민등록등본");
            }));

    assertThat(f.published)
        .singleElement()
        .isInstanceOfSatisfying(
            BenefitUpdated.class,
            e -> {
              assertThat(e.benefitId()).isEqualTo(id);
              assertThat(e.version()).isEqualTo(2);
              assertThat(e.changedFields())
                  .containsExactly("schedule", "supports", "conditions", "application");
              assertThat(e.reprocess()).isFalse();
            });
  }

  @Test
  void 칸마다_어느_부분이_바뀌었는지_고른다() {
    record Case(String name, java.util.function.Consumer<ObjectNode> change, String expected) {}
    List<Case> cases =
        List.of(
            new Case("기관", p -> p.withObject("source").put("agency", "다른 기관"), "basic"),
            new Case("지역 범위", p -> p.withObject("source").put("regionScope", "SIDO"), "region"),
            new Case(
                "지역 코드",
                p -> p.withObject("source").putArray("regionCodes").add("52730").add("52000"),
                "region"),
            new Case(
                "시작일", p -> p.withObject("schedule").put("applyStart", "2026-10-02"), "schedule"),
            new Case("상시", p -> p.withObject("schedule").put("applyAlways", true), "schedule"),
            new Case(
                "사업 시작",
                p -> p.withObject("schedule").put("businessStart", "2026-02-01"),
                "schedule"),
            new Case(
                "사업 끝", p -> p.withObject("schedule").put("businessEnd", "2026-11-30"), "schedule"),
            new Case(
                "지원 종류",
                p -> ((ObjectNode) p.withArray("supports").get(0)).put("kind", "CASH"),
                "supports"),
            new Case(
                "지원 단위",
                p -> ((ObjectNode) p.withArray("supports").get(0)).put("amountPer", "ONCE"),
                "supports"),
            new Case(
                "지원 개월",
                p -> ((ObjectNode) p.withArray("supports").get(0)).put("months", 6),
                "supports"),
            new Case(
                "지원 비율",
                p -> ((ObjectNode) p.withArray("supports").get(0)).put("ratePct", 70),
                "supports"),
            new Case(
                "지원 줄 수",
                p -> p.withArray("supports").add(p.withArray("supports").get(0).deepCopy()),
                "supports"),
            new Case(
                "조건 종류",
                p -> ((ObjectNode) p.withArray("conditions").get(0)).put("type", "OTHER"),
                "conditions"),
            new Case(
                "조건 묶음",
                p -> ((ObjectNode) p.withArray("conditions").get(0)).put("group", 9),
                "conditions"),
            new Case("조건 줄 수", p -> p.withArray("conditions").remove(0), "conditions"),
            new Case("문의처", p -> p.put("contact", "063-000-0000"), "application"),
            new Case(
                "신청 주소",
                p -> p.withObject("source").put("applyUrl", "https://example.com/apply"),
                "application"));
    for (Case c : cases) {
      UUID raw = UUID.randomUUID();
      f.ingest.apply(BenefitFixture.event(raw, 1, p -> {}));
      f.published.clear();

      f.ingest.apply(BenefitFixture.event(raw, 2, c.change()));

      assertThat(f.published)
          .as(c.name())
          .singleElement()
          .isInstanceOfSatisfying(
              BenefitUpdated.class,
              e -> assertThat(e.changedFields()).containsExactly(c.expected()));
    }
  }

  @Test
  void AI가_다시_쓴_글만_바뀌면_알리지_않는다() {
    UUID raw = UUID.randomUUID();
    f.ingest.apply(BenefitFixture.event(raw, 1, p -> {}));
    f.published.clear();

    f.ingest.apply(
        BenefitFixture.event(
            raw,
            2,
            p -> {
              p.put("summary", "다시 쓴 요약");
              p.put("howToApply", "다시 쓴 신청 방법");
              p.withObject("schedule").put("rawText", "1월 23일부터 2월 2일까지");
              ((ObjectNode) p.withArray("supports").get(0))
                  .put("rawText", "다시 쓴 원문")
                  .put("evidence", "근거");
              ((ObjectNode) p.withArray("conditions").get(0))
                  .put("evidence", "다른 근거")
                  .put("confidence", 0.9);
              ((ObjectNode) p.withArray("supports").get(0)).put("ratePct", 50.0); // 50과 50.0은 같아요
            }));

    assertThat(f.published).isEmpty();
  }

  @Test
  void 재처리_중_바뀐_것은_재처리_표시를_달아_알리고_숨겨지면_알리지_않는다() {
    UUID raw = UUID.randomUUID();
    f.ingest.apply(BenefitFixture.event(raw, 1, p -> {}));
    f.published.clear();

    f.ingest.apply(
        BenefitFixture.event(
            raw,
            2,
            p -> {
              p.put("reprocess", true);
              p.withObject("source").put("title", "새 제목");
            }));
    f.ingest.apply(BenefitFixture.event(raw, 3, p -> p.put("relevant", false)));

    assertThat(f.published)
        .singleElement()
        .isInstanceOfSatisfying(
            BenefitUpdated.class,
            e -> {
              assertThat(e.changedFields()).containsExactly("basic");
              assertThat(e.reprocess()).isTrue();
            });
  }

  @Test
  void 큰_버전은_고치고_줄을_다시_넣고_같거나_작은_버전은_버린다() {
    UUID raw = UUID.randomUUID();
    f.ingest.apply(BenefitFixture.event(raw, 2, p -> {}));
    UUID id = f.repository.findByRawPolicyId(raw).orElseThrow().id();

    f.ingest.apply(BenefitFixture.event(raw, 1, p -> p.withObject("source").put("title", "예전 제목")));
    f.ingest.apply(
        BenefitFixture.event(
            raw,
            3,
            p -> {
              p.withObject("source").put("title", "새 제목");
              p.withArray("conditions").remove(8);
            }));

    assertThat(
            f.jdbc.queryForObject(
                "select title from benefit.benefits where id = ?", String.class, id))
        .isEqualTo("새 제목");
    assertThat(count("benefit_conditions", id)).isEqualTo(8);
    assertThat(f.repository.findByRawPolicyId(raw).orElseThrow().version()).isEqualTo(3);
    assertThat(f.published)
        .as("처음 한 번 새 혜택, 고친 건 바뀜으로 (작은 버전은 버려서 알리지 않아요)")
        .extracting(Object::getClass)
        .containsExactly((Class) BenefitPublished.class, BenefitUpdated.class);
    assertThat(((BenefitUpdated) f.published.get(1)).changedFields())
        .containsExactly("basic", "conditions");
  }

  @Test
  void 같은_버전의_검수_결과는_고치고_검수_아닌_같은_버전은_버린다() {
    // 2026-11-10 코드 검토: 검수 승인·반려가 검수 전 결과와 같은 버전으로 와서 버려졌음
    UUID raw = UUID.randomUUID();
    f.ingest.apply(
        BenefitFixture.event(raw, 1, p -> p.withObject("quality").put("needsReview", true)));
    UUID id = f.repository.findByRawPolicyId(raw).orElseThrow().id();
    f.published.clear();

    f.ingest.apply(
        BenefitFixture.event(
            raw,
            1,
            p -> {
              p.put("reprocess", true);
              p.withObject("source").put("title", "검수로 고친 제목");
              p.withObject("quality").put("reviewed", true);
            }));
    f.ingest.apply(
        BenefitFixture.event(raw, 1, p -> p.withObject("source").put("title", "다시 뽑은 제목")));

    var row =
        f.jdbc.queryForMap("select title, needs_review from benefit.benefits where id = ?", id);
    assertThat(row.get("title")).isEqualTo("검수로 고친 제목");
    assertThat(row.get("needs_review")).isEqualTo(false);
    assertThat(f.published)
        .singleElement()
        .isInstanceOfSatisfying(
            BenefitUpdated.class,
            e -> {
              assertThat(e.changedFields()).containsExactly("basic");
              assertThat(e.reprocess()).isTrue();
            });

    f.ingest.apply(
        BenefitFixture.event(
            raw,
            1,
            p -> {
              p.put("reprocess", true);
              p.put("relevant", false);
              p.withObject("quality").put("reviewed", true);
            }));
    assertThat(
            f.jdbc.queryForObject(
                "select status from benefit.benefits where id = ?", String.class, id))
        .as("반려도 같은 버전으로 와서 숨겨요")
        .isEqualTo("HIDDEN");
  }

  @Test
  void 범위_밖이거나_재처리면_알리지_않고_범위_밖은_숨긴다() {
    UUID hidden = f.benefit(p -> p.put("relevant", false));
    f.benefit(p -> p.put("reprocess", true));

    assertThat(f.published).isEmpty();
    assertThat(f.queries.forJudgment(hidden)).isEmpty();
  }

  @Test
  void 주거_혜택이_아니면_저장하지_않는다() {
    UUID raw = UUID.randomUUID();
    f.ingest.apply(BenefitFixture.event(raw, 1, p -> p.put("field", "STARTUP_SUPPORT")));

    assertThat(f.repository.findByRawPolicyId(raw)).isEmpty();
  }

  @Test
  void 계약에_맞지_않으면_실패() {
    String bad = BenefitFixture.event(UUID.randomUUID(), 1, p -> p.remove("supports"));

    assertThatThrownBy(() -> f.ingest.apply(bad))
        .isInstanceOf(PolicyExtractedEvent.InvalidEventException.class)
        .hasMessageContaining("SCHEMA");
  }

  @Test
  void 날짜가_지나면_상태를_바꾸고_마감은_알린다() {
    UUID id =
        f.benefit(
            p ->
                p.withObject("schedule")
                    .put("applyStart", "2026-09-01")
                    .put("applyEnd", "2026-10-21"));
    f.jdbc.update("update benefit.benefits set status = 'OPEN' where id = ?", id);
    f.published.clear();

    f.status.refresh();

    assertThat(
            f.jdbc.queryForObject(
                "select status from benefit.benefits where id = ?", String.class, id))
        .isEqualTo("CLOSED");
    assertThat(f.published)
        .filteredOn(e -> e instanceof BenefitClosed c && c.benefitId().equals(id))
        .hasSize(1);
  }
}
