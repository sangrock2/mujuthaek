package kr.mujuthaek.api.notice.service;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import java.util.UUID;
import kr.mujuthaek.api.area.service.NoticeAreaQueryService.NoticeSite;
import org.junit.jupiter.api.Test;

/** 목록 생활권 점수: 단지가 여럿이면 가장 높은 단지 점수 (첫 단지가 아니에요). */
class NoticeBestLivingScoreTest {

  private static NoticeSite site(String id, Integer score) {
    return new NoticeSite(id, UUID.randomUUID(), 37.5, 127.0, false, List.of(), score);
  }

  @Test
  void theHighestSiteScoreRepresentsTheNotice() {
    assertThat(
            NoticeQueryService.bestLivingScore(
                List.of(site("a", 61), site("b", null), site("c", 82), site("d", 74))))
        .isEqualTo(82);
  }

  @Test
  void withoutAnyScoreItIsNull() {
    assertThat(NoticeQueryService.bestLivingScore(List.of(site("a", null)))).isNull();
    assertThat(NoticeQueryService.bestLivingScore(List.of())).isNull();
  }
}
