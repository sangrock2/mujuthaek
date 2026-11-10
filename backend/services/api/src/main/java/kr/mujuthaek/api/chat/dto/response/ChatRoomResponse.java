package kr.mujuthaek.api.chat.dto.response;

import java.time.LocalDate;
import java.util.UUID;

/**
 * 채팅방 정보.
 *
 * @param noticeId 방 ID. 물은 공고가 다른 공고에 합쳐졌으면 남은 공고 ID라 물은 ID와 달라요 (SSE·목록은 어느 쪽으로 불러도 같은 방)
 * @param readOnly true면 보내기·답장·좋아요를 막아요 (신고와 내 글 삭제는 돼요)
 * @param readOnlyFrom 읽기 전용이 되는 날 (접수 마감일 + 31일). 상시 공고는 null
 * @param guide 채팅방 위에 늘 보여줄 안내 문구
 */
public record ChatRoomResponse(
    UUID noticeId, boolean readOnly, LocalDate readOnlyFrom, String guide) {}
