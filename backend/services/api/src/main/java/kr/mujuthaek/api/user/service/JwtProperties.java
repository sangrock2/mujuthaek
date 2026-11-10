package kr.mujuthaek.api.user.service;

import java.nio.charset.StandardCharsets;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * JWT 설정 (application.yml의 app.jwt.*).
 *
 * @param secret HS256 서명 키. 32바이트 이상이어야 해요
 * @param accessTokenTtl access token 유효 시간 (Authorization: Bearer)
 * @param refreshTokenTtl refresh token 유효 시간 = 로그인 유지 기간 (HttpOnly 쿠키)
 * @param cookieSecure refresh token 쿠키를 HTTPS에서만 보낼지 (운영 true)
 */
@ConfigurationProperties("app.jwt")
public record JwtProperties(
    String secret,
    String issuer,
    Duration accessTokenTtl,
    Duration refreshTokenTtl,
    boolean cookieSecure) {

  public JwtProperties {
    if (secret == null || secret.getBytes(StandardCharsets.UTF_8).length < 32) {
      throw new IllegalStateException("app.jwt.secret(JWT_SECRET)은 32바이트 이상이어야 해요");
    }
  }

  public byte[] secretBytes() {
    return secret.getBytes(StandardCharsets.UTF_8);
  }
}
