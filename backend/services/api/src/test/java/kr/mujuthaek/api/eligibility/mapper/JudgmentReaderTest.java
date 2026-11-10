package kr.mujuthaek.api.eligibility.mapper;

import static org.assertj.core.api.Assertions.assertThat;

import java.nio.file.Files;
import java.nio.file.Path;
import java.time.LocalDate;
import kr.mujuthaek.api.eligibility.rule.ApplicantBuilder;
import kr.mujuthaek.api.eligibility.rule.CriterionJudge;
import kr.mujuthaek.api.eligibility.rule.IncomeBenchmarks;
import kr.mujuthaek.api.eligibility.rule.Judgment;
import kr.mujuthaek.api.eligibility.rule.Status;
import kr.mujuthaek.api.notice.NoticeFixtures;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.JsonNode;

/** 계약의 판정 예시(contracts/tests/fixtures/judgment/housing-examples.json, 서리풀 청년주택)를 읽어요. */
public class JudgmentReaderTest {

  /** 서리풀 청년주택 판정 틀 (다른 판정 테스트도 써요). */
  public static JsonNode example() throws Exception {
    Path root = Path.of("").toAbsolutePath();
    while (!Files.isDirectory(root.resolve("contracts"))) {
      root = root.getParent();
    }
    return NoticeFixtures.JSON
        .readTree(
            Files.readString(
                root.resolve("contracts/tests/fixtures/judgment/housing-examples.json")))
        .get(0);
  }

  @Test
  void readsGroupsAndCriteria() throws Exception {
    Judgment j = JudgmentReader.read(example());

    assertThat(j.referenceDate()).isEqualTo(LocalDate.of(2026, 10, 16));
    var artist = j.groups().get(0);
    assertThat(artist.name()).isEqualTo("문화예술분야 청년예술인");
    assertThat(artist.criteria())
        .map(c -> c.getClass().getSimpleName())
        .containsExactly("Ask", "Age", "Residence", "Homeless", "AnyOf");
    var anyOf = (Judgment.AnyOf) artist.criteria().get(4);
    assertThat(anyOf.options()).hasSize(2);
    var income50 = (Judgment.Income) anyOf.options().get(0).criteria().get(0);
    assertThat(income50.printedTable()).hasSize(5);
    assertThat(income50.bonuses()).hasSize(2);
  }

  @Test
  void incomeOrAssetsOptionIsJudgedFromThePrintedTable() throws Exception {
    Judgment j = JudgmentReader.read(example());
    var anyOf = j.groups().get(0).criteria().get(4);
    // 1인 가구, 2025년 도시근로자 70~80%(월 266만~305만 원): 50% 표(266만)는 넘지만 70% 표(343만) 안 → 두 번째 선택지로 충족
    var a = new ApplicantBuilder().household(1).income("URBAN_WORKER_INCOME", 70, 80).build();
    IncomeBenchmarks urban2025 =
        (standard, year, size) ->
            "URBAN_WORKER_INCOME".equals(standard) && year == 2025 && size == 1 ? 3_813_363L : null;

    var item = CriterionJudge.judge(anyOf, a, j.referenceDate(), urban2025);

    assertThat(item.status()).isEqualTo(Status.MET);
    assertThat(item.options())
        .extracting(o -> o.status())
        .containsExactly(Status.NOT_MET, Status.MET);
  }

  @Test
  void unknownCriterionKindsBecomeQuestions() {
    var node =
        NoticeFixtures.JSON.readTree(
            "{\"kind\":\"PET\",\"id\":\"pet\",\"quote\":\"반려동물 금지\",\"inReview\":false}");

    var c = JudgmentReader.criterion(node);

    assertThat(c).isInstanceOf(Judgment.Ask.class);
    assertThat(((Judgment.Ask) c).question()).isEqualTo("반려동물 금지");
  }
}
