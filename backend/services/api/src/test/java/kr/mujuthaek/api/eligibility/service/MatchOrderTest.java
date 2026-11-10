package kr.mujuthaek.api.eligibility.service;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.LocalDate;
import java.util.List;
import java.util.Map;
import java.util.OptionalLong;
import java.util.UUID;
import kr.mujuthaek.api.eligibility.dto.request.JudgmentApplicantRequest;
import kr.mujuthaek.api.eligibility.model.MatchResult;
import kr.mujuthaek.api.eligibility.model.NoticeCandidate;
import kr.mujuthaek.api.eligibility.rule.Eligibility;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

/** 목록 정렬: 지원 가능 → 확인 필요, 지원 가능 안에서는 내 순위(1순위 → 2순위 → … → 순위 없음), 그다음 마감 빠른 순이에요. 스프링 없이 돌아요. */
class MatchOrderTest {

  private static final JsonMapper JSON = JsonMapper.builder().build();

  private static final UUID RANK_1_LATE = UUID.fromString("00000000-0000-0000-0000-000000000001");
  private static final UUID RANK_2 = UUID.fromString("00000000-0000-0000-0000-000000000002");
  private static final UUID RANK_3 = UUID.fromString("00000000-0000-0000-0000-000000000003");
  private static final UUID NO_RANK_EARLIEST =
      UUID.fromString("00000000-0000-0000-0000-000000000004");
  private static final UUID TO_CHECK = UUID.fromString("00000000-0000-0000-0000-000000000005");

  /** 1990년생: 만 19~20세 조건은 불충족, 만 19~99세 조건은 충족이에요. */
  private static final JudgmentApplicantRequest BORN_1990 =
      JSON.convertValue(Map.of("birthDate", "1990-01-01"), JudgmentApplicantRequest.class);

  private static final String YOUNG =
      "{\"id\": \"%s\", \"kind\": \"AGE\", \"minAge\": 19, \"maxAge\": 20}";
  private static final String ADULT =
      "{\"id\": \"%s\", \"kind\": \"AGE\", \"minAge\": 19, \"maxAge\": 99}";
  private static final String ASK =
      "{\"id\": \"%s\", \"kind\": \"ASK\", \"question\": \"예술인인가요?\", \"metWhen\": \"YES\"}";

  private final MatchQueryService service =
      new MatchQueryService(
          field ->
              List.of(
                  // 1순위는 불충족, 2순위 충족 → 내 순위 2
                  notice(
                      RANK_2,
                      "2026-10-25",
                      group("r1", 1, YOUNG.formatted("r1-age")),
                      group("r2", 2, ADULT.formatted("r2-age"))),
                  // 마감은 가장 늦지만 1순위 → 지원 가능 중 맨 앞
                  notice(RANK_1_LATE, "2026-11-30", group("r1", 1, ADULT.formatted("r1-age"))),
                  notice(RANK_3, "2026-10-22", group("r3", 3, ADULT.formatted("r3-age"))),
                  // 순위 없는 공고는 마감이 가장 빨라도 순위 있는 공고 뒤
                  notice(
                      NO_RANK_EARLIEST, "2026-10-21", group("all", null, ADULT.formatted("age"))),
                  // 질문에 답이 없어 확인 필요 → 지원 가능 공고 모두 뒤
                  notice(TO_CHECK, "2026-10-20", group("r1", 1, ASK.formatted("artist")))),
          new JudgmentQueryService(
              (kind, year, program, size) -> OptionalLong.empty(),
              (day, region, area) -> OptionalLong.empty()));

  @Test
  void eligibleNoticesComeFirstRankThenDeadline() {
    MatchResult result = service.matchHousing(BORN_1990);

    assertThat(result.items())
        .extracting(MatchResult.Item::noticeId)
        .containsExactly(RANK_1_LATE, RANK_2, RANK_3, NO_RANK_EARLIEST, TO_CHECK);
    assertThat(result.items())
        .extracting(MatchResult.Item::status)
        .containsExactly(
            Eligibility.ELIGIBLE,
            Eligibility.ELIGIBLE,
            Eligibility.ELIGIBLE,
            Eligibility.ELIGIBLE,
            Eligibility.NEEDS_INPUT);
    assertThat(result.counts()).isEqualTo(new MatchResult.Counts(4, 1, 0));
  }

  @Test
  void resultCarriesMyRank() {
    MatchResult result = service.matchHousing(BORN_1990);

    assertThat(result.items())
        .extracting(MatchResult.Item::rank)
        .containsExactly(1, 2, 3, null, null);
    // 지원 가능이면 충족한 대상군만 보여요 (1순위 불충족인 공고는 2순위 대상군만)
    assertThat(result.items().get(1).groups()).containsExactly("r2");
  }

  private static String group(String id, Integer rank, String criterion) {
    return "{\"id\": \"%s\", \"name\": \"%s\", \"rank\": %s, \"criteria\": [%s]}"
        .formatted(id, id, rank, criterion);
  }

  private static NoticeCandidate notice(UUID id, String applyEnd, String... groups) {
    JsonNode frame =
        JSON.readTree(
            """
            {"schema": "housing-judgment.v1", "rawPostId": "p", "rawVersion": 1,
             "referenceDate": "2026-10-16", "common": [], "groups": [%s], "notes": []}"""
                .formatted(String.join(", ", groups)));
    return new NoticeCandidate(
        id, false, 1, id.toString(), null, LocalDate.parse(applyEnd), List.of(), frame, null);
  }
}
