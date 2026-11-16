package kr.mujuthaek.api.user.service;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.time.Clock;
import java.time.Instant;
import java.util.Base64;
import java.util.HexFormat;
import java.util.UUID;
import kr.mujuthaek.api.common.exception.CustomException;
import kr.mujuthaek.api.common.exception.ErrorCode;
import kr.mujuthaek.api.user.domain.RefreshToken;
import kr.mujuthaek.api.user.domain.User;
import kr.mujuthaek.api.user.repository.AdminUserRepository;
import kr.mujuthaek.api.user.repository.RefreshTokenRepository;
import kr.mujuthaek.api.user.repository.UserRepository;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.security.oauth2.jose.jws.MacAlgorithm;
import org.springframework.security.oauth2.jwt.JwsHeader;
import org.springframework.security.oauth2.jwt.JwtClaimsSet;
import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.security.oauth2.jwt.JwtEncoderParameters;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 토큰 발급·재발급·폐기.
 *
 * <ul>
 *   <li>access token: JWT (HS256). sub = 회원 ID, role, nickname. 서버에 저장하지 않아요
 *   <li>refresh token: 무작위 32바이트. DB에는 해시만 두고 한 번만 사용해요. 재사용되면 해당 로그인 계보를 폐기해요
 * </ul>
 */
@Service
public class AuthTokenService {

  public static final String ROLE_CLAIM = "role";
  public static final String NICKNAME_CLAIM = "nickname";
  public static final String SESSION_CLAIM = "sid";
  public static final String AUTH_TIME_CLAIM = "auth_time";
  static final int MAX_ISSUED_PER_MINUTE = 30;

  private final JwtEncoder jwtEncoder;
  private final JwtProperties props;
  private final RefreshTokenRepository refreshTokens;
  private final UserRepository users;
  private final AdminUserRepository admins;
  private static final SecureRandom RANDOM = new SecureRandom();

  private final Clock clock;

  @Autowired
  public AuthTokenService(
      JwtEncoder jwtEncoder,
      JwtProperties props,
      RefreshTokenRepository refreshTokens,
      UserRepository users,
      AdminUserRepository admins) {
    this(jwtEncoder, props, refreshTokens, users, admins, Clock.systemUTC());
  }

  AuthTokenService(
      JwtEncoder jwtEncoder,
      JwtProperties props,
      RefreshTokenRepository refreshTokens,
      UserRepository users,
      AdminUserRepository admins,
      Clock clock) {
    this.jwtEncoder = jwtEncoder;
    this.props = props;
    this.refreshTokens = refreshTokens;
    this.users = users;
    this.admins = admins;
    this.clock = clock;
  }

  /** 소셜 로그인 성공 직후: access + refresh 발급. 이용 정지 중이면 ACCOUNT_SUSPENDED. */
  @Transactional
  public TokenPair issue(LoginUser user) {
    Instant now = clock.instant();
    UUID familyId = UUID.randomUUID();
    users.lockById(user.userId()).orElseThrow(() -> new CustomException(ErrorCode.UNAUTHENTICATED));
    notSuspended(user.userId(), now);
    checkIssueLimit(user.userId(), now);
    return new TokenPair(
        accessToken(user, familyId, now, now),
        props.accessTokenTtl(),
        newRefreshToken(user.userId(), familyId, now, now),
        props.refreshTokenTtl());
  }

  /**
   * refresh token으로 새 access token 발급. refresh token도 새로 바꿔요. 권한·닉네임은 DB의 지금 값을 써요 (ADMIN으로 바꾸면 다음
   * 재발급부터 적용).
   *
   * <p>사용한 값의 해시를 원래 만료일까지 보관해 재사용을 감지해요. 재사용 시 새로 발급한 토큰도 같은 계보 전체를 폐기합니다.
   */
  @Transactional(noRollbackFor = CustomException.class) // 만료된 값도 지운 채로 401을 보내요
  public TokenPair refresh(String rawRefreshToken) {
    String tokenHash = hash(rawRefreshToken);
    UUID userId =
        refreshTokens
            .findUserIdByTokenHash(tokenHash)
            .orElseThrow(() -> new CustomException(ErrorCode.INVALID_REFRESH_TOKEN));
    User user =
        users
            .lockById(userId)
            .orElseThrow(() -> new CustomException(ErrorCode.INVALID_REFRESH_TOKEN));
    // 잠금을 얻은 뒤 시각과 토큰을 다시 확인해, 기다리는 동안의 로그아웃·회전도 반영해요.
    Instant now = clock.instant();
    RefreshToken saved =
        refreshTokens
            .findByTokenHash(tokenHash)
            .orElseThrow(() -> new CustomException(ErrorCode.INVALID_REFRESH_TOKEN));
    if (saved.expired(now)) {
      refreshTokens.deleteByTokenHash(tokenHash);
      throw new CustomException(ErrorCode.INVALID_REFRESH_TOKEN);
    }
    if (saved.getRotatedAt() != null) throw reused(saved);
    checkIssueLimit(userId, now);
    if (refreshTokens.markRotated(tokenHash, now) == 0) throw reused(saved);
    notSuspended(user.getId(), now);
    var login = new LoginUser(user.getId(), user.getNickname(), user.getRole().name());
    return new TokenPair(
        accessToken(login, saved.getFamilyId(), saved.getAuthenticatedAt(), now),
        props.accessTokenTtl(),
        newRefreshToken(user.getId(), saved.getFamilyId(), saved.getAuthenticatedAt(), now),
        props.refreshTokenTtl());
  }

  /** 로그아웃: 이 로그인에서 파생된 토큰을 모두 지워요. 다른 기기 로그인은 유지해요. */
  @Transactional
  public void revoke(String rawRefreshToken) {
    String tokenHash = hash(rawRefreshToken);
    refreshTokens
        .findUserIdByTokenHash(tokenHash)
        .ifPresent(
            userId -> {
              if (users.lockById(userId).isPresent()) {
                refreshTokens
                    .findByTokenHash(tokenHash)
                    .ifPresent(saved -> refreshTokens.deleteFamily(userId, saved.getFamilyId()));
              }
            });
  }

  /** 모든 기기에서 로그아웃. 계보를 확인하는 access token도 다음 요청부터 거부해요. */
  @Transactional
  public void revokeAll(UUID userId) {
    if (users.lockById(userId).isPresent()) {
      refreshTokens.deleteByUserId(userId);
    }
  }

  /** 원래 유효기간이 끝난 토큰만 정리해요. 사용한 해시는 만료 전 재사용 감지를 위해 남겨요. */
  @Transactional
  public int deleteExpired() {
    Instant now = clock.instant();
    return refreshTokens.deleteExpired(now);
  }

  @Transactional(readOnly = true)
  public boolean activeSession(UUID userId, UUID familyId) {
    return refreshTokens.activeFamily(userId, familyId, clock.instant());
  }

  /** 이용 정지 중이면 로그인·재발급을 막아요 (정지할 때 로그인도 모두 끊어요). */
  private void notSuspended(UUID userId, Instant now) {
    if (admins.suspended(userId, now)) {
      throw new CustomException(ErrorCode.ACCOUNT_SUSPENDED);
    }
  }

  private void checkIssueLimit(UUID userId, Instant now) {
    if (refreshTokens.recentlyIssued(userId, now.minusSeconds(60)) >= MAX_ISSUED_PER_MINUTE) {
      throw new CustomException(ErrorCode.RATE_LIMITED);
    }
  }

  private CustomException reused(RefreshToken token) {
    refreshTokens.deleteFamily(token.getUserId(), token.getFamilyId());
    LoggerFactory.getLogger(AuthTokenService.class)
        .warn("Refresh token reuse detected; login revoked: userId={}", token.getUserId());
    return new CustomException(ErrorCode.INVALID_REFRESH_TOKEN);
  }

  private String accessToken(LoginUser user, UUID familyId, Instant authenticatedAt, Instant now) {
    var claims =
        JwtClaimsSet.builder()
            .issuer(props.issuer())
            .subject(user.userId().toString())
            .issuedAt(now)
            .expiresAt(now.plus(props.accessTokenTtl()))
            .claim(ROLE_CLAIM, user.role())
            .claim(NICKNAME_CLAIM, user.nickname() == null ? "" : user.nickname())
            .claim(SESSION_CLAIM, familyId.toString())
            .claim(AUTH_TIME_CLAIM, authenticatedAt.getEpochSecond())
            .build();
    var header = JwsHeader.with(MacAlgorithm.HS256).build();
    return jwtEncoder.encode(JwtEncoderParameters.from(header, claims)).getTokenValue();
  }

  private String newRefreshToken(UUID userId, UUID familyId, Instant authenticatedAt, Instant now) {
    String raw = randomToken();
    refreshTokens.save(
        new RefreshToken(
            userId, familyId, hash(raw), now.plus(props.refreshTokenTtl()), now, authenticatedAt));
    return raw;
  }

  /** 무작위 32바이트, URL에 그대로 쓸 수 있는 Base64. refresh token·탈퇴 티켓이 같이 써요 (DB에는 {@link #hash}만). */
  static String randomToken() {
    byte[] bytes = new byte[32];
    RANDOM.nextBytes(bytes);
    return Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
  }

  static String hash(String raw) {
    try {
      byte[] digest =
          MessageDigest.getInstance("SHA-256").digest(raw.getBytes(StandardCharsets.UTF_8));
      return HexFormat.of().formatHex(digest);
    } catch (NoSuchAlgorithmException e) {
      throw new IllegalStateException(e);
    }
  }
}
