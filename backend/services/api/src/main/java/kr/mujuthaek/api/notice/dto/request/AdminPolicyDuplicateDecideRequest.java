package kr.mujuthaek.api.notice.dto.request;

import jakarta.validation.constraints.NotBlank;

/**
 * 관리자 「중복 의심」 처리 본문.
 *
 * @param action KEEP_BOTH(둘 다 둠) · HIDE_LATER(나중 것 숨김)
 */
public record AdminPolicyDuplicateDecideRequest(@NotBlank String action) {}
