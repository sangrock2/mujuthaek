package kr.mujuthaek.api.common.event;

import java.util.UUID;

/**
 * 회원이 탈퇴함 (user 모듈의 회원·소셜 계정·토큰은 이미 삭제됨). 회원 데이터를 가진 다른 모듈(알림 설정·푸시 구독 등)은 이 이벤트를 받아 자기 데이터를 지워요
 * (요구사항 3-16: 탈퇴 후 데이터 0건).
 */
public record UserWithdrawn(UUID userId) {}
