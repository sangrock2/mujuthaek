package kr.mujuthaek.api.chat.domain;

import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

/**
 * 채팅방 = 공고 하나. 정정으로 공고 버전이 바뀌어도 같은 방이에요.
 *
 * @param noticeId 방 ID. 다른 공고에 합쳐진 공고면 남은 공고 ID
 * @param applyEnd 접수 마감일. 상시 공고는 null
 * @param mergedNoticeIds 이 공고에 합쳐진 공고 ID들. 합치기 전에 쓴 메시지는 그 ID에 남아 있어 방 목록에 함께 보여요
 */
public record ChatRoom(UUID noticeId, LocalDate applyEnd, List<UUID> mergedNoticeIds) {

  /** 접수 마감 뒤 이만큼 지나면 읽기 전용이에요. */
  public static final int READ_ONLY_AFTER_DAYS = 30;

  public ChatRoom {
    mergedNoticeIds = mergedNoticeIds == null ? List.of() : List.copyOf(mergedNoticeIds);
  }

  public ChatRoom(UUID noticeId, LocalDate applyEnd) {
    this(noticeId, applyEnd, List.of());
  }

  /** 이 방의 메시지가 달린 공고 ID들 (방 ID + 합쳐진 공고 ID). */
  public List<UUID> noticeIds() {
    List<UUID> ids = new ArrayList<>(mergedNoticeIds.size() + 1);
    ids.add(noticeId);
    ids.addAll(mergedNoticeIds);
    return ids;
  }

  /** 읽기 전용이 되는 날 (이날부터). 마감일이 없는 공고는 null: 읽기 전용이 되지 않아요. */
  public LocalDate readOnlyFrom() {
    return applyEnd == null ? null : applyEnd.plusDays(READ_ONLY_AFTER_DAYS + 1);
  }

  /** 접수 마감일 + 30일 < 오늘이면 읽기 전용 (보내기·답장·좋아요를 막아요). */
  public boolean readOnly(LocalDate today) {
    LocalDate from = readOnlyFrom();
    return from != null && !today.isBefore(from);
  }
}
