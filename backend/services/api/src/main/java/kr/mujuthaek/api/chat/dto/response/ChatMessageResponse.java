package kr.mujuthaek.api.chat.dto.response;

import java.time.OffsetDateTime;
import java.util.UUID;
import kr.mujuthaek.api.chat.domain.MessageStatus;

/**
 * 메시지 하나 (목록, 보내기 응답, SSE message.created·message.restored가 같은 모양).
 *
 * @param noticeId 채팅방 (공고 ID)
 * @param authorNickname 작성자 닉네임. 닉네임이 없으면 null
 * @param content 본문. VISIBLE이 아니면(삭제·가림) null이라 화면은 status로 안내 문구를 골라요
 * @param likedByMe 로그인한 사람이 좋아요를 눌렀는지. 비로그인·SSE로 받은 메시지는 false
 * @param mine 로그인한 사람이 쓴 글인지(삭제 메뉴용). 비로그인·SSE로 받은 메시지는 false
 * @param parent 답장이면 원문 미리보기, 아니면 null
 */
public record ChatMessageResponse(
    UUID id,
    UUID noticeId,
    String authorNickname,
    String content,
    MessageStatus status,
    int likeCount,
    boolean likedByMe,
    boolean mine,
    Parent parent,
    OffsetDateTime createdAt) {

  /**
   * 답장 대상 미리보기.
   *
   * @param content 원문 앞 50자. 원문이 VISIBLE이 아니면 null
   * @param status 원문 상태. 원문 작성자가 탈퇴해 원문이 지워졌으면 DELETED (authorNickname도 null)
   */
  public record Parent(UUID id, String authorNickname, String content, MessageStatus status) {}
}
