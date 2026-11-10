package kr.mujuthaek.api.area;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;
import java.time.Instant;
import java.util.UUID;
import kr.mujuthaek.api.TestcontainersConfiguration;
import kr.mujuthaek.api.notice.NoticeFixtures;
import kr.mujuthaek.api.notice.dto.response.NoticeDetailResponse;
import kr.mujuthaek.api.notice.service.NoticeQueryService;
import kr.mujuthaek.api.notice.service.internal.NoticeIngestionService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.JdbcTemplate;

/**
 * 공고 반영부터 공고 상세의 지역 점수까지 앱 전체로 (연결 PR 검증 항목): notice가 공고를 반영하며 NoticeLocationsChanged를 보내면 area가 커밋
 * 뒤 비동기로 좌표·지표·점수를 계산해 AreaScoresCalculated를 보내고, notice가 받아 상세 areaSummaries에 보여요. 검색 API 키는 없는
 * 환경이에요.
 */
@SpringBootTest(properties = "spring.rabbitmq.listener.simple.auto-startup=false")
@Import(TestcontainersConfiguration.class)
class NoticeAreaLinkIntegrationTest {

  @Autowired NoticeIngestionService ingestion;
  @Autowired NoticeQueryService notices;
  @Autowired JdbcTemplate jdbc;

  @Test
  void aPublishedNoticeGetsItsAreaScoreOnTheDetail() throws Exception {
    // 계약 예시 공고의 위치(서울특별시 종로구 가상로 1)를 사전에 넣어요
    jdbc.update(
        "insert into area.address_points (address_id, load_scope, bjd_code, sigungu_code, road_code, road_name,"
            + " underground, bldg_main, bldg_sub, geom, data_date) values ('11110101999999900000100000', '11',"
            + " '1111010100', '11110', '111109999999', '가상로', 0, 1, 0, st_makepoint(126.98, 37.57)::geography,"
            + " date '2026-09-30') on conflict do nothing");

    UUID rawPostId = UUID.randomUUID();
    ingestion.apply(NoticeFixtures.envelope(NoticeFixtures.payload(rawPostId, 1)));
    UUID noticeId =
        jdbc.queryForObject(
            "select id from notice.notices where raw_post_id = ?", UUID.class, rawPostId);

    NoticeDetailResponse detail = waitForAreaScore(noticeId);

    assertThat(detail.areaSummaries())
        .singleElement()
        .satisfies(
            s -> {
              assertThat(s.siteId()).isEqualTo("building-a");
              assertThat(s.kind()).isEqualTo("LIVING");
              assertThat(s.score())
                  .isBetween(java.math.BigDecimal.ZERO, java.math.BigDecimal.valueOf(100));
            });
    assertThat(
            jdbc.queryForObject(
                "select status from area.notice_locations where notice_id = ?",
                String.class,
                noticeId))
        .isEqualTo("OK");
  }

  private NoticeDetailResponse waitForAreaScore(UUID noticeId) throws InterruptedException {
    Instant until = Instant.now().plus(Duration.ofSeconds(30));
    while (true) {
      NoticeDetailResponse detail = notices.detail(noticeId);
      if (!detail.areaSummaries().isEmpty() || Instant.now().isAfter(until)) {
        return detail;
      }
      Thread.sleep(200);
    }
  }
}
