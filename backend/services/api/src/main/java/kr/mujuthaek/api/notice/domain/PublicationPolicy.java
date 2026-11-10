package kr.mujuthaek.api.notice.domain;

import java.time.LocalDate;

/**
 * 받은 추출 결과를 공개할지 정하는 규칙. 스프링·DB 없이 값만 보고 정해요.
 *
 * <ul>
 *   <li>검수 대기·상세 없음은 공개하지 않고, 이미 공개된 공고는 그대로 둬요.
 *   <li>자동 통과·부분 게시·승인은 공개해요. 공고가 있으면 새 버전으로 바꿔요.
 *   <li>같은 원본 글에서 이미 반영한 버전보다 낮으면 오래된 결과라 버려요(원본 버전은 글마다 따로 세요).
 *   <li>같은 원본 버전의 승인본이 공개돼 있으면 자동 결과로 바꾸지 않아요.
 *   <li>정정 공고가 반영된 뒤에 온 원래 공고의 결과는 정정 내용을 덮어쓰지 않아요.
 *   <li>이미 반영한 다른 정정보다 게시일이 이른 정정이 늦게 오면 반영하지 않아요(게시일을 모르면 도착 순서대로).
 *   <li>후속 안내도 같은 원본 버전의 승인본이 붙어 있으면 자동 결과로 바꾸지 않아요.
 *   <li>내용이 같으면 새 버전을 만들지 않아요.
 * </ul>
 */
public final class PublicationPolicy {

  private PublicationPolicy() {}

  /**
   * 지금 공개된 공고의 정보. 공고가 없으면 null을 넘겨요.
   *
   * @param sourceRawVersion 받은 결과와 같은 원본 글에서 마지막으로 반영한 원본 버전. 이 글에서 반영한 적이 없으면 null
   * @param sourceReviewStatus 그 버전의 검수 상태 (sourceRawVersion이 null이면 null)
   * @param corrected 정정 공고가 반영된 공고인지
   * @param otherCorrectionPostedOn 받은 글이 아닌, 이미 반영한 정정 공고의 가장 늦은 게시일 (없거나 모르면 null)
   */
  public record Published(
      Integer sourceRawVersion,
      ReviewStatus sourceReviewStatus,
      String contentHash,
      boolean corrected,
      LocalDate otherCorrectionPostedOn) {

    public Published(
        Integer sourceRawVersion,
        ReviewStatus sourceReviewStatus,
        String contentHash,
        boolean corrected) {
      this(sourceRawVersion, sourceReviewStatus, contentHash, corrected, null);
    }
  }

  /**
   * 받은 결과. hasDetail은 payload.notice(상세)가 있는지, correction은 정정 공고인지, postedOn은 원본 글 게시일 (모르면 null).
   */
  public record Incoming(
      int rawVersion,
      ReviewStatus reviewStatus,
      boolean hasDetail,
      String contentHash,
      boolean correction,
      LocalDate postedOn) {

    public Incoming(
        int rawVersion,
        ReviewStatus reviewStatus,
        boolean hasDetail,
        String contentHash,
        boolean correction) {
      this(rawVersion, reviewStatus, hasDetail, contentHash, correction, null);
    }
  }

  /** 결정. reason은 공개하지 않을 때의 이유 코드. */
  public record Decision(IngestionOutcome outcome, String reason) {

    /** 공고 내용이 공개됨 (새 공고 또는 새 버전). 이 글을 기다리던 정정·후속 안내를 이어서 반영해요. */
    public boolean publishes() {
      return outcome == IngestionOutcome.PUBLISHED || outcome == IngestionOutcome.NEW_VERSION;
    }
  }

  public static Decision decide(Published current, Incoming in) {
    if (!in.hasDetail()) {
      return new Decision(IngestionOutcome.HELD, "DETAIL_MISSING");
    }
    if (!in.reviewStatus().publishable()) {
      return new Decision(IngestionOutcome.HELD, "IN_REVIEW");
    }
    if (current == null) {
      return new Decision(IngestionOutcome.PUBLISHED, null);
    }
    Integer applied = current.sourceRawVersion();
    if (applied != null && in.rawVersion() < applied) {
      return new Decision(IngestionOutcome.STALE, "OLDER_RAW_VERSION");
    }
    if (applied != null
        && in.rawVersion() == applied
        && current.sourceReviewStatus() == ReviewStatus.APPROVED
        && in.reviewStatus() != ReviewStatus.APPROVED) {
      return new Decision(IngestionOutcome.KEPT_APPROVED, "APPROVED_ALREADY_PUBLISHED");
    }
    if (!in.correction() && current.corrected()) {
      return new Decision(IngestionOutcome.KEPT_CORRECTION, "CORRECTION_ALREADY_APPLIED");
    }
    if (in.correction()
        && in.postedOn() != null
        && current.otherCorrectionPostedOn() != null
        && in.postedOn().isBefore(current.otherCorrectionPostedOn())) {
      // 정정 공고는 글마다 원본 버전을 따로 세서 버전으로 비교할 수 없어요. 게시일이 더 이른 정정이 늦게 오면 최신 정정을 덮어쓰지 않아요
      return new Decision(IngestionOutcome.KEPT_CORRECTION, "LATER_CORRECTION_APPLIED");
    }
    if (in.contentHash().equals(current.contentHash())) {
      return applied != null && approves(applied, current.sourceReviewStatus(), in)
          ? new Decision(IngestionOutcome.APPROVAL_RECORDED, null)
          : new Decision(IngestionOutcome.NO_CHANGE, null);
    }
    return new Decision(IngestionOutcome.NEW_VERSION, null);
  }

  /**
   * 공개된 자동 결과와 내용이 같은 승인본인지. 내용 해시에는 검수 상태가 없어 그냥 두면 「변화 없음」으로 끝나고 승인 기록이 남지 않아, 뒤에 같은 원본 버전의 다른 자동
   * 결과(재처리)가 승인 내용을 덮어써요(2026-10-21 검토). 새 버전 없이 검수 상태만 승인으로 올려요.
   */
  private static boolean approves(int appliedRawVersion, ReviewStatus appliedStatus, Incoming in) {
    return in.reviewStatus() == ReviewStatus.APPROVED
        && in.rawVersion() == appliedRawVersion
        && appliedStatus != ReviewStatus.APPROVED;
  }

  /** 이미 붙인 후속 안내. 없으면 null. reviewStatus는 붙인 결과의 검수 상태. */
  public record AttachedFollowUp(int rawVersion, String contentHash, ReviewStatus reviewStatus) {}

  /**
   * 후속 안내(2-15)를 원래 공고에 붙일지. 공고 스냅샷은 바꾸지 않고 후속 안내만 따로 붙여요.
   *
   * @param parentPublished 원래 공고가 공개돼 있는지. 아니면 공개될 때까지 기다려요
   */
  public static Decision decideFollowUp(
      AttachedFollowUp attached, Incoming in, boolean parentPublished) {
    if (!in.hasDetail()) {
      return new Decision(IngestionOutcome.HELD, "DETAIL_MISSING");
    }
    if (!in.reviewStatus().publishable()) {
      return new Decision(IngestionOutcome.HELD, "IN_REVIEW");
    }
    if (!parentPublished) {
      return new Decision(IngestionOutcome.HELD, "PARENT_NOT_PUBLISHED");
    }
    if (attached != null && in.rawVersion() < attached.rawVersion()) {
      return new Decision(IngestionOutcome.STALE, "OLDER_RAW_VERSION");
    }
    if (attached != null
        && in.rawVersion() == attached.rawVersion()
        && attached.reviewStatus() == ReviewStatus.APPROVED
        && in.reviewStatus() != ReviewStatus.APPROVED) {
      return new Decision(IngestionOutcome.KEPT_APPROVED, "APPROVED_ALREADY_PUBLISHED");
    }
    if (attached != null && in.contentHash().equals(attached.contentHash())) {
      return approves(attached.rawVersion(), attached.reviewStatus(), in)
          ? new Decision(IngestionOutcome.APPROVAL_RECORDED, null)
          : new Decision(IngestionOutcome.NO_CHANGE, null);
    }
    return new Decision(IngestionOutcome.FOLLOW_UP_ATTACHED, null);
  }
}
