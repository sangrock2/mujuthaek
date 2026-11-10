package kr.mujuthaek.api.chat.dto.request;

import jakarta.validation.constraints.NotNull;
import kr.mujuthaek.api.chat.domain.ReviewAction;

/** 관리자의 신고 처리: 가림 유지(KEEP_HIDDEN) 또는 다시 보이기(RESTORE). */
public record ReviewRequest(@NotNull ReviewAction action) {}
