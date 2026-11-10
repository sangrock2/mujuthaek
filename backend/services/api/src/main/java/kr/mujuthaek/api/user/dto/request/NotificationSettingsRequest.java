package kr.mujuthaek.api.user.dto.request;

import jakarta.validation.constraints.NotNull;

/** 알림 설정 저장 본문 (PUT /api/users/me/notification-settings). 모든 칸을 보내요. */
public record NotificationSettingsRequest(
    @NotNull Boolean newNotice,
    @NotNull Boolean newSupport,
    @NotNull Boolean deadline,
    @NotNull Boolean correction,
    @NotNull Boolean followUp,
    @NotNull Boolean quietEnabled) {}
