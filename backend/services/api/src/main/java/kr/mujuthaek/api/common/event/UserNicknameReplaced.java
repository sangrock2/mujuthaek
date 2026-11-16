package kr.mujuthaek.api.common.event;

import java.util.UUID;

/**
 * 실명일 수 있는 회원 닉네임(예전에 구글 이름을 그대로 쓴 것)을 별칭으로 바꿨어요. 작성자 이름을 따로 저장한 모듈(채팅)은 지난 글의 이름도 이 별칭으로 바꿔요
 * (2026-11-16 보안 감사 L-8).
 */
public record UserNicknameReplaced(UUID userId, String nickname) {}
