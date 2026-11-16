package kr.mujuthaek.api.user.security;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.jwt.Jwt;

class AuthenticationTimeClaimsTest {
  @Test
  void currentPrincipalGetsOriginalAuthTimeWhileLegacyTokenHasNoRecentAuthentication() {
    var builder =
        Jwt.withTokenValue("synthetic")
            .header("alg", "HS256")
            .subject(UUID.randomUUID().toString())
            .claim("role", "SUPER_ADMIN")
            .claim("sid", UUID.randomUUID().toString());
    var converter = new LoginUserJwtConverter();
    var legacy = (LoginAuthenticationToken) converter.convert(builder.build());
    assertThat(legacy.getPrincipal().authenticatedAt()).isNull();
    Instant original = Instant.parse("2026-11-16T00:00:00Z");
    var current =
        (LoginAuthenticationToken)
            converter.convert(builder.claim("auth_time", original.getEpochSecond()).build());
    assertThat(current.getPrincipal().authenticatedAt()).isEqualTo(original);
  }
}
