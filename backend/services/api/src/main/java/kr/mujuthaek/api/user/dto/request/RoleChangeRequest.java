package kr.mujuthaek.api.user.dto.request;

import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;

/** 관리자 지정(ADMIN)·해제(USER). 최상위(SUPER_ADMIN)는 여기서 바꿀 수 없어요(넘기기만). */
public record RoleChangeRequest(@NotNull @Pattern(regexp = "USER|ADMIN") String role) {}
