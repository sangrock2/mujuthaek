package kr.mujuthaek.api.notice.dto.response;

import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.util.List;

/**
 * 관리자 검수 대기 목록 (오래된 것부터, 최대 50건).
 *
 * @param total 이 목록의 건수(사유로 거르기 전)
 */
public record AdminReviewListResponse(int total, List<Item> items) {

  /**
   * 대기 한 건.
   *
   * @param id 검수 작업 ID (승인·반려에 써요)
   * @param reason MUST 공개 전 꼭 볼 것 · CHECK 공개됐지만 보류한 칸이 있음 · FORMAT 원본 자료 문제(글자를 못 읽음 등)
   * @param title 추출한 공고 제목, 없으면 수집한 글 제목
   * @param sourceCode 수집 출처 코드 (예: lh_myhome)
   * @param rawVersion 원문 버전
   * @param issueCount 사람이 볼 이슈 수
   * @param applyEndsOn 신청 일정 중 가장 이른 마감일 (모르면 null)
   */
  public record Item(
      String id,
      String reason,
      String title,
      String sourceCode,
      Integer rawVersion,
      OffsetDateTime receivedAt,
      int issueCount,
      LocalDate applyEndsOn) {}
}
