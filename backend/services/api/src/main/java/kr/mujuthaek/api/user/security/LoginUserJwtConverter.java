package kr.mujuthaek.api.user.security;

import java.util.UUID;
import kr.mujuthaek.api.user.service.AuthTokenService;
import kr.mujuthaek.api.user.service.LoginUser;
import org.springframework.core.convert.converter.Converter;
import org.springframework.security.authentication.AbstractAuthenticationToken;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.stereotype.Component;

/** 검증된 access token → {@link LoginUser}. 컨트롤러는 {@code @AuthenticationPrincipal LoginUser}로 받아요. */
@Component
class LoginUserJwtConverter implements Converter<Jwt, AbstractAuthenticationToken> {

  @Override
  public AbstractAuthenticationToken convert(Jwt jwt) {
    String nickname = jwt.getClaimAsString(AuthTokenService.NICKNAME_CLAIM);
    var user =
        new LoginUser(
            UUID.fromString(jwt.getSubject()),
            nickname == null || nickname.isEmpty() ? null : nickname,
            jwt.getClaimAsString(AuthTokenService.ROLE_CLAIM));
    return UsernamePasswordAuthenticationToken.authenticated(user, jwt, user.getAuthorities());
  }
}
