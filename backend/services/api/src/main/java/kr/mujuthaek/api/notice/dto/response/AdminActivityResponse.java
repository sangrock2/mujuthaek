package kr.mujuthaek.api.notice.dto.response;

import java.time.OffsetDateTime;
import java.util.List;

/**
 * 관리자 「처리 기록」: 검수(공고·혜택)와 제보(공고·혜택·창업 사업·생활권) 처리를 최근 순으로.
 *
 * @param reviewsError 검수 기록을 못 받았으면 이유(추출 서비스가 꺼진 경우 등). 제보 기록은 그대로 와요
 */
public record AdminActivityResponse(int days, List<Item> items, String reviewsError) {

  /**
   * 기록 한 줄.
   *
   * @param kind
   *     NOTICE_REVIEW·BENEFIT_REVIEW·NOTICE_REPORT·BENEFIT_REPORT·PROGRAM_REPORT·AREA_REPORT
   * @param action 검수는 APPROVED·EDITED_APPROVED·REJECTED·REOPENED, 제보는 FIXED·KEPT
   * @param title 대상 제목 (모르면 null)
   * @param detail 검수 메모 또는 제보한 칸 이름
   * @param by 처리한 관리자 (로그인 계정 ID, 모르면 null). 이름은 화면이 회원 관리 API로 찾아요
   * @param targetId 검수 작업·검수 ID 또는 제보 ID
   */
  public record Item(
      OffsetDateTime at,
      String kind,
      String action,
      String title,
      String detail,
      String by,
      String targetId) {}
}
