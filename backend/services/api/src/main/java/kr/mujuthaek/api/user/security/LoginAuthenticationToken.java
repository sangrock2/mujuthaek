package kr.mujuthaek.api.user.security;

import java.io.Serial;
import java.util.UUID;
import kr.mujuthaek.api.user.service.LoginUser;
import org.springframework.security.authentication.AbstractAuthenticationToken;

/** 검증한 회원과 로그인 계보만 보관해요. 원문 JWT를 인증 객체에 남기지 않아요. */
final class LoginAuthenticationToken extends AbstractAuthenticationToken {
  @Serial private static final long serialVersionUID = 1L;
  private final LoginUser user;
  private final UUID sessionId;

  LoginAuthenticationToken(LoginUser user, UUID sessionId) {
    super(user.getAuthorities());
    this.user = user;
    this.sessionId = sessionId;
    setAuthenticated(true);
  }

  UUID sessionId() {
    return sessionId;
  }

  @Override
  public Object getCredentials() {
    return "";
  }

  @Override
  public LoginUser getPrincipal() {
    return user;
  }
}
