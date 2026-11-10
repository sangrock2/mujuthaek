package kr.mujuthaek.api.notice.domain;

import static kr.mujuthaek.api.notice.domain.ReviewStatus.APPROVED;
import static kr.mujuthaek.api.notice.domain.ReviewStatus.AUTO_PASSED;
import static kr.mujuthaek.api.notice.domain.ReviewStatus.IN_REVIEW;
import static kr.mujuthaek.api.notice.domain.ReviewStatus.PARTIALLY_PASSED;
import static org.assertj.core.api.Assertions.assertThat;

import kr.mujuthaek.api.notice.domain.PublicationPolicy.Decision;
import kr.mujuthaek.api.notice.domain.PublicationPolicy.Incoming;
import kr.mujuthaek.api.notice.domain.PublicationPolicy.Published;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.EnumSource;

class PublicationPolicyTest {

  /** 같은 원본 글에서 반영한 공고 (정정 없음). */
  private static Published published(int rawVersion, ReviewStatus status, String hash) {
    return new Published(rawVersion, status, hash, false);
  }

  private static Decision decide(
      Published current, int rawVersion, ReviewStatus status, String hash) {
    return PublicationPolicy.decide(current, new Incoming(rawVersion, status, true, hash, false));
  }

  private static Decision correction(Published current, int rawVersion, String hash) {
    return PublicationPolicy.decide(
        current, new Incoming(rawVersion, AUTO_PASSED, true, hash, true));
  }

  @ParameterizedTest
  @EnumSource(names = {"AUTO_PASSED", "PARTIALLY_PASSED", "APPROVED"})
  void 공고가_없으면_공개할_수_있는_결과는_공개한다(ReviewStatus status) {
    Decision decision = decide(null, 1, status, "h");

    assertThat(decision.outcome()).isEqualTo(IngestionOutcome.PUBLISHED);
    assertThat(decision.publishes()).isTrue();
  }

  @Test
  void 검수_대기는_공고가_없어도_있어도_공개하지_않는다() {
    assertThat(decide(null, 1, IN_REVIEW, "h"))
        .isEqualTo(new Decision(IngestionOutcome.HELD, "IN_REVIEW"));
    assertThat(decide(published(1, AUTO_PASSED, "h"), 2, IN_REVIEW, "x").outcome())
        .isEqualTo(IngestionOutcome.HELD);
  }

  @Test
  void 상세가_없으면_공개하지_않는다() {
    Decision decision =
        PublicationPolicy.decide(null, new Incoming(1, AUTO_PASSED, false, "h", false));

    assertThat(decision).isEqualTo(new Decision(IngestionOutcome.HELD, "DETAIL_MISSING"));
    assertThat(decision.publishes()).isFalse();
  }

  @Test
  void 같은_글의_낮은_원본_버전은_오래된_결과로_버린다() {
    assertThat(decide(published(3, AUTO_PASSED, "h"), 2, APPROVED, "x"))
        .isEqualTo(new Decision(IngestionOutcome.STALE, "OLDER_RAW_VERSION"));
  }

  @Test
  void 같은_원본_버전의_승인본은_자동_결과로_바꾸지_않는다() {
    Published approved = published(2, APPROVED, "h");

    assertThat(decide(approved, 2, AUTO_PASSED, "x").outcome())
        .isEqualTo(IngestionOutcome.KEPT_APPROVED);
    assertThat(decide(approved, 2, PARTIALLY_PASSED, "x").outcome())
        .isEqualTo(IngestionOutcome.KEPT_APPROVED);
    assertThat(decide(approved, 2, APPROVED, "x").outcome())
        .isEqualTo(IngestionOutcome.NEW_VERSION);
    assertThat(decide(approved, 3, AUTO_PASSED, "x").outcome())
        .isEqualTo(IngestionOutcome.NEW_VERSION);
  }

  @Test
  void 내용이_같으면_새_버전을_만들지_않고_다르면_새_버전() {
    Published current = published(1, PARTIALLY_PASSED, "h");

    assertThat(decide(current, 1, AUTO_PASSED, "h").outcome())
        .isEqualTo(IngestionOutcome.NO_CHANGE);
    assertThat(decide(current, 2, AUTO_PASSED, "x").outcome())
        .isEqualTo(IngestionOutcome.NEW_VERSION);
  }

  @Test
  void 정정_공고는_처음_반영할_때_원래_글의_버전과_비교하지_않는다() {
    // 정정 글에서 반영한 적이 없으면 원본 버전 1이어도 새 버전이에요 (원본 버전은 글마다 따로 세요)
    Published original = new Published(null, null, "h", false);

    assertThat(correction(original, 1, "x").outcome()).isEqualTo(IngestionOutcome.NEW_VERSION);
    assertThat(correction(new Published(2, AUTO_PASSED, "x", true), 1, "y").outcome())
        .isEqualTo(IngestionOutcome.STALE);
  }

  @Test
  void 후속_안내는_원래_공고가_공개돼_있을_때만_붙인다() {
    Incoming followUp = new Incoming(1, AUTO_PASSED, true, "f", false);

    assertThat(PublicationPolicy.decideFollowUp(null, followUp, true).outcome())
        .isEqualTo(IngestionOutcome.FOLLOW_UP_ATTACHED);
    assertThat(PublicationPolicy.decideFollowUp(null, followUp, false))
        .isEqualTo(new Decision(IngestionOutcome.HELD, "PARENT_NOT_PUBLISHED"));
    assertThat(
            PublicationPolicy.decideFollowUp(
                null, new Incoming(1, IN_REVIEW, true, "f", false), true))
        .isEqualTo(new Decision(IngestionOutcome.HELD, "IN_REVIEW"));
    assertThat(
            PublicationPolicy.decideFollowUp(
                null, new Incoming(1, AUTO_PASSED, false, "f", false), true))
        .isEqualTo(new Decision(IngestionOutcome.HELD, "DETAIL_MISSING"));
  }

  @Test
  void 이미_붙인_후속_안내는_새_버전이고_내용이_다를_때만_바꾼다() {
    PublicationPolicy.AttachedFollowUp attached =
        new PublicationPolicy.AttachedFollowUp(2, "f", AUTO_PASSED);

    assertThat(
            PublicationPolicy.decideFollowUp(
                    attached, new Incoming(2, AUTO_PASSED, true, "f", false), true)
                .outcome())
        .isEqualTo(IngestionOutcome.NO_CHANGE);
    assertThat(
            PublicationPolicy.decideFollowUp(
                    attached, new Incoming(1, AUTO_PASSED, true, "x", false), true)
                .outcome())
        .isEqualTo(IngestionOutcome.STALE);
    assertThat(
            PublicationPolicy.decideFollowUp(
                    attached, new Incoming(3, AUTO_PASSED, true, "x", false), true)
                .outcome())
        .isEqualTo(IngestionOutcome.FOLLOW_UP_ATTACHED);
  }

  @Test
  void 정정이_반영된_뒤_온_원래_공고_결과는_정정을_덮어쓰지_않는다() {
    Published corrected = new Published(1, AUTO_PASSED, "c", true);

    assertThat(decide(corrected, 2, AUTO_PASSED, "x"))
        .isEqualTo(new Decision(IngestionOutcome.KEPT_CORRECTION, "CORRECTION_ALREADY_APPLIED"));
    assertThat(correction(corrected, 2, "y").outcome()).isEqualTo(IngestionOutcome.NEW_VERSION);
  }

  @Test
  void 늦게_도착한_더_이른_정정은_최신_정정을_덮어쓰지_않는다() {
    // 정정 B(10-15 게시)가 먼저 반영된 뒤 정정 A(10-10 게시)가 옴. 둘 다 원래 공고를 가리키고 원본 버전은 글마다 따로 세요
    Published afterB =
        new Published(null, null, "b", true, java.time.LocalDate.parse("2026-10-15"));

    assertThat(
            PublicationPolicy.decide(
                afterB,
                new Incoming(
                    1, AUTO_PASSED, true, "a", true, java.time.LocalDate.parse("2026-10-10"))))
        .isEqualTo(new Decision(IngestionOutcome.KEPT_CORRECTION, "LATER_CORRECTION_APPLIED"));
    assertThat(
            PublicationPolicy.decide(
                    afterB,
                    new Incoming(
                        1, AUTO_PASSED, true, "c", true, java.time.LocalDate.parse("2026-10-18")))
                .outcome())
        .isEqualTo(IngestionOutcome.NEW_VERSION);
    // 게시일을 모르면 도착 순서대로 반영해요
    assertThat(correction(afterB, 1, "d").outcome()).isEqualTo(IngestionOutcome.NEW_VERSION);
  }

  @Test
  void 공개된_자동_결과와_내용이_같은_승인본은_검수_상태만_올린다() {
    Published auto = published(3, AUTO_PASSED, "h");

    assertThat(decide(auto, 3, APPROVED, "h").outcome())
        .isEqualTo(IngestionOutcome.APPROVAL_RECORDED);
    assertThat(decide(published(3, APPROVED, "h"), 3, APPROVED, "h").outcome())
        .isEqualTo(IngestionOutcome.NO_CHANGE);
    assertThat(decide(auto, 3, AUTO_PASSED, "h").outcome()).isEqualTo(IngestionOutcome.NO_CHANGE);
    assertThat(
            PublicationPolicy.decideFollowUp(
                    new PublicationPolicy.AttachedFollowUp(2, "f", AUTO_PASSED),
                    new Incoming(2, APPROVED, true, "f", false),
                    true)
                .outcome())
        .isEqualTo(IngestionOutcome.APPROVAL_RECORDED);
  }

  @Test
  void 승인한_후속_안내는_같은_원본_버전의_자동_결과로_바꾸지_않는다() {
    PublicationPolicy.AttachedFollowUp approved =
        new PublicationPolicy.AttachedFollowUp(2, "f", APPROVED);

    assertThat(
            PublicationPolicy.decideFollowUp(
                approved, new Incoming(2, AUTO_PASSED, true, "x", false), true))
        .isEqualTo(new Decision(IngestionOutcome.KEPT_APPROVED, "APPROVED_ALREADY_PUBLISHED"));
    assertThat(
            PublicationPolicy.decideFollowUp(
                    approved, new Incoming(3, AUTO_PASSED, true, "x", false), true)
                .outcome())
        .isEqualTo(IngestionOutcome.FOLLOW_UP_ATTACHED);
    assertThat(
            PublicationPolicy.decideFollowUp(
                    approved, new Incoming(2, APPROVED, true, "x", false), true)
                .outcome())
        .isEqualTo(IngestionOutcome.FOLLOW_UP_ATTACHED);
  }
}
