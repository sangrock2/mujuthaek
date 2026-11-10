package kr.mujuthaek.api.chat.dto.response;

import java.util.UUID;

/**
 * 좋아요·좋아요 취소 결과. 낙관적 업데이트를 이 값으로 맞춰요.
 *
 * @param liked 지금 내가 좋아요한 상태인지
 */
public record LikeResponse(UUID messageId, int likeCount, boolean liked) {}
