package kr.mujuthaek.api.chat.dto.request;

import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import kr.mujuthaek.api.chat.domain.ReportReason;

/**
 * 메시지 신고.
 *
 * @param detail 기타 사유 (200자까지)
 */
public record ReportRequest(@NotNull ReportReason reason, @Size(max = 200) String detail) {}
