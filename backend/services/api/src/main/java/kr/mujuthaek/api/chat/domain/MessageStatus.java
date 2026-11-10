package kr.mujuthaek.api.chat.domain;

/** 메시지 상태. 화면은 VISIBLE이 아니면 본문 대신 안내 문구를 보여줘요. */
public enum MessageStatus {
  /** 보임 */
  VISIBLE,
  /** 작성자가 지움 ("삭제된 메시지입니다"). 본문은 신고 검토용으로 DB에 남고 응답에서는 숨겨요 (작성자가 탈퇴하면 줄째 지워요) */
  DELETED,
  /** 신고 3건으로 자동으로 가림 ("신고로 가려진 메시지입니다"). 관리자 검토 전 */
  HIDDEN_REPORTED,
  /** 관리자가 가림을 유지함 */
  HIDDEN_ADMIN;

  public boolean hidden() {
    return this == HIDDEN_REPORTED || this == HIDDEN_ADMIN;
  }
}
