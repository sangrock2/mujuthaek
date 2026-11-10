package kr.mujuthaek.api.notice.service;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.LocalDate;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import kr.mujuthaek.api.notice.NoticeApiFixture;
import kr.mujuthaek.api.notice.NoticeFixtures;
import org.junit.jupiter.api.Test;

/** 다른 모듈(알림)이 공고 ID로 묻는 공고 요약. */
class NoticeSummaryQueryTest {

  private final NoticeApiFixture f = new NoticeApiFixture();

  @Test
  void 공고_ID로_요약을_물은_순서대로_준다() {
    UUID first =
        f.notice(
            p -> {
              NoticeFixtures.region(p, "11650");
              NoticeApiFixture.schedule(p, "2026-10-26", "2026-10-30");
            });
    UUID second = f.notice(p -> NoticeFixtures.region(p, "26110"));
    UUID unknown = UUID.randomUUID();

    Map<UUID, NoticeSummary> found =
        f.queries.findSummaries(List.of(second, unknown, first, second));

    assertThat(found.keySet()).containsExactly(second, first); // 없는 공고는 빠지고 중복은 한 번
    NoticeSummary summary = found.get(first);
    assertThat(summary.noticeId()).isEqualTo(first);
    assertThat(summary.version()).isEqualTo(1);
    assertThat(summary.field()).isEqualTo("HOUSING");
    assertThat(summary.title()).isNotBlank();
    assertThat(summary.provider()).isEqualTo(f.provider);
    assertThat(summary.status()).isEqualTo("UPCOMING");
    assertThat(summary.applyStart()).isEqualTo(LocalDate.of(2026, 10, 26));
    assertThat(summary.applyEnd()).isEqualTo(LocalDate.of(2026, 10, 30));
    assertThat(summary.regionCodes()).containsExactly("1165000000");
    assertThat(summary.nationwide()).isFalse();
    assertThat(summary.detailPath()).isEqualTo("/api/v1/notices/" + first);
    assertThat(summary.detailUrl())
        .isEqualTo(
            f.jdbc.queryForObject(
                "select detail_url from notice.notices where id = ?", String.class, first));
    assertThat(found.get(second).regionCodes()).containsExactly("2611000000");
  }

  @Test
  void 전국_공고는_빈_지역_목록이고_지역을_모르면_null이다() {
    UUID nationwide = f.notice(p -> {});
    UUID unknownRegion = f.notice(p -> {});
    f.jdbc.update("update notice.notices set nationwide = true where id = ?", nationwide);
    f.jdbc.update("delete from notice.notice_regions where notice_id = ?", nationwide);
    f.jdbc.update("delete from notice.notice_regions where notice_id = ?", unknownRegion);

    Map<UUID, NoticeSummary> found = f.queries.findSummaries(List.of(nationwide, unknownRegion));

    assertThat(found.get(nationwide).nationwide()).isTrue();
    assertThat(found.get(nationwide).regionCodes()).isEmpty();
    assertThat(found.get(unknownRegion).nationwide()).isFalse();
    assertThat(found.get(unknownRegion).regionCodes()).isNull();
  }

  @Test
  void 합쳐진_공고_ID는_남은_공고의_요약을_주고_숨긴_공고는_뺀다() {
    UUID kept = f.notice(p -> {});
    UUID merged = f.notice(p -> {});
    UUID hidden = f.notice(p -> {});
    f.ingest.merge(merged, kept);
    f.jdbc.update("update notice.notices set hidden = true where id = ?", hidden);

    Map<UUID, NoticeSummary> found = f.queries.findSummaries(List.of(merged, kept, hidden));

    assertThat(found.keySet()).containsExactly(merged, kept);
    assertThat(found.get(merged).noticeId()).isEqualTo(kept);
    assertThat(found.get(merged)).isEqualTo(found.get(kept));
    assertThat(f.queries.findSummary(hidden)).isEmpty();
  }

  @Test
  void 마감된_공고도_준다() {
    UUID closed = f.notice(p -> {});
    f.jdbc.update("update notice.notices set status = 'CLOSED' where id = ?", closed);

    assertThat(f.queries.findSummary(closed))
        .hasValueSatisfying(s -> assertThat(s.status()).isEqualTo("CLOSED"));
    assertThat(f.queries.findSummaries(List.of())).isEmpty();
  }
}
