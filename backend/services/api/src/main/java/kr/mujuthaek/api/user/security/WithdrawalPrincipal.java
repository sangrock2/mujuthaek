package kr.mujuthaek.api.user.security;

import java.util.Collection;
import java.util.List;
import java.util.Map;
import kr.mujuthaek.api.user.domain.SocialProvider;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.core.user.OAuth2User;

/**
 * 탈퇴용 재인증이 끝난 상태. 로그인(가입·토큰 발급)을 하지 않고 LoginSuccessHandler가 탈퇴를 처리해요. 제공자 access token은 연결 끊기에만 쓰고
 * 저장하지 않아요 (이 요청 안에서만 살아 있어요).
 */
record WithdrawalPrincipal(
    SocialProvider provider, String providerUserId, String ticket, String providerAccessToken)
    implements OAuth2User {

  @Override
  public String getName() {
    return provider + ":" + providerUserId;
  }

  @Override
  public Map<String, Object> getAttributes() {
    return Map.of();
  }

  @Override
  public Collection<? extends GrantedAuthority> getAuthorities() {
    return List.of();
  }

  @Override
  public String toString() {
    return "WithdrawalPrincipal[" + getName() + "]"; // 토큰·티켓을 로그에 남기지 않게
  }
}
