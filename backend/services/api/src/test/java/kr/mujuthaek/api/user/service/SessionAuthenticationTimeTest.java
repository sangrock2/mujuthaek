package kr.mujuthaek.api.user.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Optional;
import java.util.UUID;
import kr.mujuthaek.api.user.domain.RefreshToken;
import kr.mujuthaek.api.user.domain.Role;
import kr.mujuthaek.api.user.domain.User;
import kr.mujuthaek.api.user.repository.AdminUserRepository;
import kr.mujuthaek.api.user.repository.RefreshTokenRepository;
import kr.mujuthaek.api.user.repository.UserRepository;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.security.oauth2.jwt.JwtEncoderParameters;

class SessionAuthenticationTimeTest {
  private static final Instant NOW = Instant.parse("2026-11-16T03:00:00Z");

  @Test
  void refreshKeepsOriginalAuthenticationTimeAndNewLoginStartsItsOwnTime() {
    UUID id = UUID.randomUUID();
    UUID family = UUID.randomUUID();
    Instant original = NOW.minusSeconds(3600);
    User user = mock(User.class);
    when(user.getId()).thenReturn(id);
    when(user.getRole()).thenReturn(Role.USER);
    var users = mock(UserRepository.class);
    when(users.lockById(id)).thenReturn(Optional.of(user));
    var repository = mock(RefreshTokenRepository.class);
    String hash = AuthTokenService.hash("synthetic-refresh");
    when(repository.findUserIdByTokenHash(hash)).thenReturn(Optional.of(id));
    when(repository.findByTokenHash(hash))
        .thenReturn(
            Optional.of(
                new RefreshToken(
                    id, family, hash, NOW.plusSeconds(3600), NOW.minusSeconds(60), original)));
    when(repository.markRotated(hash, NOW)).thenReturn(1);
    var encoder = mock(JwtEncoder.class);
    when(encoder.encode(any()))
        .thenReturn(
            Jwt.withTokenValue("synthetic").header("alg", "HS256").subject(id.toString()).build());
    var properties =
        new JwtProperties(
            "s".repeat(32), "test", Duration.ofMinutes(30), Duration.ofDays(30), true);
    var service =
        new AuthTokenService(
            encoder,
            properties,
            repository,
            users,
            mock(AdminUserRepository.class),
            Clock.fixed(NOW, ZoneOffset.UTC));

    service.refresh("synthetic-refresh");
    service.issue(new LoginUser(id, null, "USER"));

    var claims = ArgumentCaptor.forClass(JwtEncoderParameters.class);
    verify(encoder, times(2)).encode(claims.capture());
    assertThat(
            claims
                .getAllValues()
                .get(0)
                .getClaims()
                .getClaims()
                .get(AuthTokenService.AUTH_TIME_CLAIM))
        .isEqualTo(original.getEpochSecond());
    assertThat(
            claims
                .getAllValues()
                .get(1)
                .getClaims()
                .getClaims()
                .get(AuthTokenService.AUTH_TIME_CLAIM))
        .isEqualTo(NOW.getEpochSecond());
    var saved = ArgumentCaptor.forClass(RefreshToken.class);
    verify(repository, times(2)).save(saved.capture());
    assertThat(saved.getAllValues())
        .extracting(RefreshToken::getAuthenticatedAt)
        .containsExactly(original, NOW);
  }
}
