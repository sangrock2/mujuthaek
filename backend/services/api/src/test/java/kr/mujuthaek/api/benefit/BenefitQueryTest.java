package kr.mujuthaek.api.benefit;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.LocalDate;
import java.util.List;
import java.util.UUID;
import kr.mujuthaek.api.benefit.service.BenefitForJudgment;
import kr.mujuthaek.api.benefit.service.BenefitSummary;
import org.junit.jupiter.api.Test;

/** 판정 후보 조회: 지역 겹침, 숨김·마감 제외, 금액은 원. 알림용 요약·마감 임박. */
class BenefitQueryTest {

  private final BenefitFixture f = new BenefitFixture();

  @Test
  void 알림용_요약은_숨긴_혜택도_준다() {
    UUID id = f.benefit(region("SIDO", "11"));
    UUID hidden = f.benefit(p -> p.put("relevant", false));

    BenefitSummary s = f.queries.findSummary(id).orElseThrow();
    assertThat(s.field()).isEqualTo("BENEFIT");
    assertThat(s.version()).isEqualTo(1);
    assertThat(s.status()).isEqualTo("OPEN");
    assertThat(s.applyEnd()).isEqualTo(LocalDate.of(2026, 11, 30));
    assertThat(s.regionScope()).isEqualTo("SIDO");
    assertThat(s.regionCodes()).containsExactly("11");
    assertThat(f.queries.findSummary(hidden).orElseThrow().status()).isEqualTo("HIDDEN");
    assertThat(f.queries.findSummary(UUID.randomUUID())).isEmpty();
  }

  @Test
  void 여러_혜택_요약을_한_번에_읽어도_하나씩_읽은_것과_같다() {
    UUID id = f.benefit(region("SIDO", "11"));
    UUID hidden = f.benefit(p -> p.put("relevant", false));
    UUID missing = UUID.randomUUID();

    var many = f.queries.findSummaries(List.of(id, hidden, missing, id));

    assertThat(many).containsOnlyKeys(id, hidden); // 없는 ID는 빠지고, 숨김은 줘요
    assertThat(many.get(id)).isEqualTo(f.queries.findSummary(id).orElseThrow());
    assertThat(many.get(hidden)).isEqualTo(f.queries.findSummary(hidden).orElseThrow());
    assertThat(f.queries.findSummaries(List.of())).isEmpty();
  }

  @Test
  void 수집_정책_ID로도_요약을_찾는다() {
    // 혜택 제보 답변 이벤트(BenefitReportAnswered)의 policyId는 수집 정책 ID라서
    UUID raw = UUID.randomUUID();
    f.ingest.apply(BenefitFixture.event(raw, 1, p -> {}));
    UUID id = f.repository.findByRawPolicyId(raw).orElseThrow().id();

    assertThat(f.queries.findSummaryByRawPolicyId(raw).orElseThrow().benefitId()).isEqualTo(id);
    assertThat(f.queries.findSummaryByRawPolicyId(UUID.randomUUID())).isEmpty();
  }

  @Test
  void 마감_임박은_그날_마감이고_접수_중인_혜택만_준다() {
    UUID d3 = f.benefit(p -> p.withObject("schedule").put("applyEnd", "2026-10-25"));
    UUID d1 = f.benefit(p -> p.withObject("schedule").put("applyEnd", "2026-10-23"));
    UUID other = f.benefit(p -> p.withObject("schedule").put("applyEnd", "2026-10-24"));
    UUID hidden =
        f.benefit(
            p -> {
              p.put("relevant", false);
              p.withObject("schedule").put("applyEnd", "2026-10-25");
            });
    UUID always =
        f.benefit(
            p -> p.withObject("schedule").put("applyEnd", "2026-10-25").put("applyAlways", true));
    UUID notStarted =
        f.benefit(
            p ->
                p.withObject("schedule")
                    .put("applyStart", "2026-10-23")
                    .put("applyEnd", "2026-10-25"));

    List<UUID> ids =
        f
            .queries
            .findOpenClosingOn(
                List.of(LocalDate.of(2026, 10, 25), LocalDate.of(2026, 10, 23)),
                BenefitFixture.TODAY)
            .stream()
            .map(BenefitSummary::benefitId)
            .toList();
    assertThat(ids).contains(d1, d3).doesNotContain(other, hidden, always, notStarted);
    assertThat(ids.indexOf(d1)).as("마감일 순").isLessThan(ids.indexOf(d3));
    assertThat(f.queries.findOpenClosingOn(List.of(), BenefitFixture.TODAY)).isEmpty();
  }

  private static java.util.function.Consumer<tools.jackson.databind.node.ObjectNode> region(
      String scope, String... codes) {
    return p -> {
      var source = p.withObject("source");
      source.put("regionScope", scope);
      var arr = source.putArray("regionCodes");
      for (String c : codes) arr.add(c);
    };
  }

  private List<UUID> ids(List<String> filter) {
    return f.queries.openForJudgment(filter).stream().map(BenefitForJudgment::id).toList();
  }

  @Test
  void 찾아볼_지역과_겹치는_혜택과_전국_혜택만_준다() {
    UUID mapo = f.benefit(region("SIGUNGU", "11440"));
    UUID seoul = f.benefit(region("SIDO", "11"));
    UUID busan = f.benefit(region("SIGUNGU", "26350"));
    UUID nationwide = f.benefit(region("NATIONWIDE"));
    UUID closed =
        f.benefit(
            region("SIGUNGU", "11440")
                .andThen(p -> p.withObject("schedule").put("applyEnd", "2026-10-01")));

    assertThat(ids(List.of("11440")))
        .contains(mapo, seoul, nationwide)
        .doesNotContain(busan, closed);
    assertThat(ids(List.of("11"))).contains(mapo, seoul, nationwide).doesNotContain(busan);
    assertThat(ids(List.of())).contains(mapo, seoul, busan, nationwide).doesNotContain(closed);

    // 2026-11-10 재검토: 일반구가 있는 시와 그 구는 겹쳐요(장안구 회원에게 수원시 혜택이 후보에서 빠졌음). 영동군과 증평군은 아님
    UUID suwon = f.benefit(region("SIGUNGU", "41110"));
    UUID jangan = f.benefit(region("SIGUNGU", "41111"));
    UUID yeongdong = f.benefit(region("SIGUNGU", "43740"));
    assertThat(ids(List.of("41111"))).contains(suwon, jangan).doesNotContain(mapo, yeongdong);
    assertThat(ids(List.of("41110"))).contains(suwon, jangan);
    assertThat(ids(List.of("43745"))).doesNotContain(yeongdong, suwon);
  }

  @Test
  void 지원_금액은_원으로_조건은_원문과_함께_준다() {
    UUID id = f.benefit(p -> {});

    BenefitForJudgment b = f.queries.forJudgment(id).orElseThrow();
    assertThat(b.supports().getFirst().amountMaxWon()).isEqualTo(200_000L);
    assertThat(b.supports().getFirst().amountPer()).isEqualTo("MONTH");
    assertThat(b.conditions()).hasSize(9);
    assertThat(b.conditions().getFirst().valueJson()).contains("\"min\"").contains("18");
    assertThat(b.conditions().get(5).valueJson()).isNull();
  }
}
