package kr.mujuthaek.api.notice.dto.response;

import java.time.OffsetDateTime;
import java.util.List;
import java.util.UUID;

/**
 * 관리자 제보 상세. 제보한 회원이 누구인지는 보여 주지 않아요.
 *
 * @param note 이 제보의 설명 전체
 * @param notes 같은 공고·칸의 다른 제보 (맞다고 한 값·설명)
 * @param handledBy 처리한 관리자 (로그인 계정 ID)
 * @param reviewId 「고치기」로 다시 연 검수 작업 ID (없으면 null)
 */
public record AdminReportDetailResponse(
    AdminReportListResponse.Item report,
    String note,
    List<Note> notes,
    String result,
    String reply,
    String handledBy,
    OffsetDateTime startedAt,
    OffsetDateTime handledAt,
    UUID reviewId) {

  /** 같은 칸의 다른 제보 한 줄. */
  public record Note(String reportedValue, String text, String status, OffsetDateTime createdAt) {}
}
