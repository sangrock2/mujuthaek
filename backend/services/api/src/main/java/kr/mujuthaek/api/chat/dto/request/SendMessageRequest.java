package kr.mujuthaek.api.chat.dto.request;

import io.swagger.v3.oas.annotations.media.Schema;
import java.util.UUID;

/**
 * 메시지 보내기·답장.
 *
 * @param content 본문 1~500자 (앞뒤 공백은 지워요). 어기면 400 CHAT_INVALID_CONTENT, 휴대폰 번호·주민등록번호가 있으면 400
 *     CHAT_PERSONAL_INFO
 * @param parentId 답장이면 대상 메시지 ID. 답장에 답장하면 400 CHAT_REPLY_DEPTH
 */
public record SendMessageRequest(
    @Schema(requiredMode = Schema.RequiredMode.REQUIRED, minLength = 1, maxLength = 500)
        String content,
    UUID parentId) {}
