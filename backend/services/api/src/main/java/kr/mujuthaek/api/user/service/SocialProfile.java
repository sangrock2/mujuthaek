package kr.mujuthaek.api.user.service;

import java.util.Set;
import kr.mujuthaek.api.user.domain.SocialProvider;

/**
 * 소셜 로그인 제공자가 알려준 회원 정보 중 우리가 쓰는 것.
 *
 * @param providerUserId 제공자의 회원번호 (카카오 id)
 * @param nickname 없을 수 있어요 (동의하지 않은 경우, 구글처럼 실명만 주는 제공자)
 * @param realNames 제공자가 준 실명일 수 있는 이름 (구글 name·given_name). 저장하지 않고, 예전에 이 이름을 닉네임으로 저장한 회원을 별칭으로
 *     바꾸는 데만 써요 (2026-11-16 보안 감사 L-8)
 */
public record SocialProfile(
    SocialProvider provider, String providerUserId, String nickname, Set<String> realNames) {

  public SocialProfile {
    realNames = realNames == null ? Set.of() : Set.copyOf(realNames);
  }

  public SocialProfile(SocialProvider provider, String providerUserId, String nickname) {
    this(provider, providerUserId, nickname, Set.of());
  }

  /** 로그·예외에 실명이 찍히지 않게 이름 목록은 빼요 */
  @Override
  public String toString() {
    return "SocialProfile[provider=" + provider + ", providerUserId=" + providerUserId + "]";
  }
}
