package kr.mujuthaek.api.user.service;

import kr.mujuthaek.api.user.domain.SocialProvider;

/**
 * 소셜 로그인 제공자가 알려준 회원 정보 중 우리가 쓰는 것.
 *
 * @param providerUserId 제공자의 회원번호 (카카오 id)
 * @param nickname 없을 수 있어요 (동의하지 않은 경우)
 */
public record SocialProfile(SocialProvider provider, String providerUserId, String nickname) {}
