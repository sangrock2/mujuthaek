package kr.mujuthaek.api.eligibility.service;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.LocalDate;
import java.util.List;
import java.util.UUID;
import kr.mujuthaek.api.eligibility.mapper.MatchMapper;
import kr.mujuthaek.api.eligibility.model.MatchResult;
import kr.mujuthaek.api.eligibility.model.NoticeCandidate;
import kr.mujuthaek.api.eligibility.rule.Field;
import kr.mujuthaek.api.notice.service.NoticeField;
import kr.mujuthaek.api.notice.service.NoticeForJudgment;
import kr.mujuthaek.api.notice.service.NoticeQueryService;
import kr.mujuthaek.api.notice.service.ProgramForJudgment;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

/**
 * 분야마다 notice의 맞는 조회에서 후보를 가져오고(주거·사업공간 → findOpenForJudgment, 창업지원 → findOpenProgramsForJudgment),
 * 값을 그대로 옮기는지 봐요.
 */
class JudgmentCandidateReaderTest {

  private static final JsonMapper JSON = JsonMapper.builder().build();
  private static final UUID SHOP = UUID.randomUUID();
  private static final UUID SPACE_POLICY = UUID.randomUUID();
  private static final UUID PROGRAM = UUID.randomUUID();
  private static final UUID UNKNOWN_REGION = UUID.randomUUID();

  private static final JsonNode SHOP_FRAME =
      JSON.readTree("{\"schema\": \"business-space-judgment.v1\"}");
  private static final JsonNode STARTUP_FRAME =
      JSON.readTree("{\"schema\": \"startup-support-judgment.v1\"}");

  private final NoticeQueryService notices =
      new NoticeQueryService(null, null, null, null, null, null, null) { // 판정용 메서드만 덮어써서 씀
        @Override
        public List<NoticeForJudgment> findOpenForJudgment(NoticeField field) {
          return switch (field) {
            case BUSINESS_SPACE ->
                List.of(
                    new NoticeForJudgment(
                        SHOP,
                        false,
                        3,
                        "행복상가",
                        LocalDate.parse("2026-10-20"),
                        LocalDate.parse("2026-10-30"),
                        List.of("1150010100"),
                        SHOP_FRAME,
                        "https://example.org/notices/shop"),
                    new NoticeForJudgment(
                        SPACE_POLICY,
                        true,
                        2,
                        "창업보육센터 입주기업 모집",
                        null,
                        LocalDate.parse("2026-11-03"),
                        List.of(),
                        SHOP_FRAME,
                        "https://example.org/policies/space"));
            case HOUSING ->
                List.of(
                    new NoticeForJudgment(
                        UNKNOWN_REGION, false, 1, "지역을 모르는 공고", null, null, null, null, null));
          };
        }

        @Override
        public List<ProgramForJudgment> findOpenProgramsForJudgment() {
          return List.of(
              new ProgramForJudgment(
                  PROGRAM,
                  1,
                  "예비창업패키지",
                  null,
                  LocalDate.parse("2026-11-05"),
                  List.of(),
                  STARTUP_FRAME,
                  "https://example.org/programs/pre-startup"));
        }
      };

  private final JudgmentCandidateReader reader = new JudgmentCandidateReader(notices);

  @Test
  void businessSpaceComesFromNoticeListWithPolicyFlagAndLink() {
    List<NoticeCandidate> candidates = reader.openNotices(Field.BUSINESS_SPACE);

    assertThat(candidates)
        .containsExactly(
            new NoticeCandidate(
                SHOP,
                false,
                3,
                "행복상가",
                LocalDate.parse("2026-10-20"),
                LocalDate.parse("2026-10-30"),
                List.of("1150010100"),
                SHOP_FRAME,
                "https://example.org/notices/shop"),
            new NoticeCandidate(
                SPACE_POLICY,
                true,
                2,
                "창업보육센터 입주기업 모집",
                null,
                LocalDate.parse("2026-11-03"),
                List.of(),
                SHOP_FRAME,
                "https://example.org/policies/space"));
    // 목록 결과에도 그대로 실려서, 화면은 정책이면 공고 상세 대신 원문 주소로 보내요
    MatchResult.Item policy = MatchMapper.notReady(candidates.get(1));
    assertThat(policy.policy()).isTrue();
    assertThat(policy.detailUrl()).isEqualTo("https://example.org/policies/space");
  }

  @Test
  void unknownRegionStaysNullNotNationwide() {
    NoticeCandidate candidate = reader.openNotices(Field.HOUSING).getFirst();

    assertThat(candidate.noticeId()).isEqualTo(UNKNOWN_REGION);
    // 빈 목록(전국)으로 바꾸지 않아요: 바꾸면 모든 지역에 맞는 공고처럼 보여요
    assertThat(candidate.regionCodes()).isNull();
    assertThat(MatchMapper.notReady(candidate).regionCodes()).isNull();
  }

  @Test
  void startupSupportComesFromProgramList() {
    assertThat(reader.openNotices(Field.STARTUP_SUPPORT))
        .containsExactly(
            new NoticeCandidate(
                PROGRAM,
                true,
                1,
                "예비창업패키지",
                null,
                LocalDate.parse("2026-11-05"),
                List.of(),
                STARTUP_FRAME,
                "https://example.org/programs/pre-startup"));
  }
}
