package kr.mujuthaek.api.user.service;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.time.Clock;
import java.time.Duration;
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
 *   <li>refresh token: 무작위 32바이트. DB에는 SHA-256 해시만. 재발급할 때마다 새 값으로 바꿔요(회전). 쓴 값은 {@link
 *       #ROTATED_GRACE} 동안만 더 받아 주고, 그 뒤로는 받지 않아요
 * </ul>
 */
@Service
public class AuthTokenService {

  public static final String ROLE_CLAIM = "role";
  public static final String NICKNAME_CLAIM = "nickname";

  /**
   * 바꾼 refresh token을 더 받아 주는 시간. 새로고침을 빠르게 하거나 탭 여러 개가 함께 연장하면, 먼저 간 요청이 바꾼 새 쿠키를 브라우저가 받기 전에 늦은
   * 요청이 옛 쿠키를 들고 와요(응답을 받기 전에 페이지를 떠나면 새 쿠키를 아예 못 받기도 해요). 그때 로그아웃되지 않게 잠깐은 옛 값으로도 연장해 줘요
   * (2026-10-29).
   */
  public static final Duration ROTATED_GRACE = Duration.ofSeconds(30);

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
    notSuspended(user.userId(), now);
    return new TokenPair(
        accessToken(user, now),
        props.accessTokenTtl(),
        newRefreshToken(user.userId(), now),
        props.refreshTokenTtl());
  }

  /**
   * refresh token으로 새 access token 발급. refresh token도 새로 바꿔요. 권한·닉네임은 DB의 지금 값을 써요 (ADMIN으로 바꾸면 다음
   * 재발급부터 적용).
   *
   * <p>쓴 값은 지우지 않고 바꾼 시각만 적어요. 같은 값이 {@link #ROTATED_GRACE} 안에 다시 오면(새로고침 연타, 탭 여러 개가 동시에 연장) 그 요청도
   * 새 토큰을 받아요. 그 뒤에 오면 401이에요. 동시에 온 요청끼리도 둘 다 새 토큰을 받고, 브라우저에는 마지막에 받은 쿠키가 남아요(어느 쪽이든 유효).
   */
  @Transactional(noRollbackFor = CustomException.class) // 만료된 값도 지운 채로 401을 보내요
  public TokenPair refresh(String rawRefreshToken) {
    Instant now = clock.instant();
    String tokenHash = hash(rawRefreshToken);
    RefreshToken saved =
        refreshTokens
            .findByTokenHash(tokenHash)
            .orElseThrow(() -> new CustomException(ErrorCode.INVALID_REFRESH_TOKEN));
    if (saved.expired(now)) {
      refreshTokens.deleteByTokenHash(tokenHash);
      throw new CustomException(ErrorCode.INVALID_REFRESH_TOKEN);
    }
    Instant rotatedAt = saved.getRotatedAt();
    if (rotatedAt == null && refreshTokens.markRotated(tokenHash, now) == 0) {
      rotatedAt = now; // 동시에 온 다른 요청이 방금 바꿨어요
    }
    if (rotatedAt != null && rotatedAt.plus(ROTATED_GRACE).isBefore(now)) {
      throw new CustomException(ErrorCode.INVALID_REFRESH_TOKEN);
    }
    User user =
        users
            .findById(saved.getUserId())
            .orElseThrow(() -> new CustomException(ErrorCode.INVALID_REFRESH_TOKEN));
    notSuspended(user.getId(), now);
    var login = new LoginUser(user.getId(), user.getNickname(), user.getRole().name());
    return new TokenPair(
        accessToken(login, now),
        props.accessTokenTtl(),
        newRefreshToken(user.getId(), now),
        props.refreshTokenTtl());
  }

  /** 로그아웃: 이 refresh token만 지워요 (다른 기기 로그인은 유지). 이미 없으면 아무것도 안 해요. */
  @Transactional
  public void revoke(String rawRefreshToken) {
    refreshTokens.deleteByTokenHash(hash(rawRefreshToken));
  }

  /** 모든 기기에서 로그아웃 (탈퇴·권한 회수 때). access token은 남은 시간(최대 accessTokenTtl)까지는 유효해요. */
  @Transactional
  public void revokeAll(UUID userId) {
    refreshTokens.deleteByUserId(userId);
  }

  /** 만료된 refresh token과, 바꾼 지 오래돼 더는 받지 않는 값 정리. */
  @Transactional
  public int deleteExpired() {
    Instant now = clock.instant();
    return refreshTokens.deleteExpired(now, now.minus(ROTATED_GRACE));
  }

  /** 이용 정지 중이면 로그인·재발급을 막아요 (정지할 때 로그인도 모두 끊어요). */
  private void notSuspended(UUID userId, Instant now) {
    if (admins.suspended(userId, now)) {
      throw new CustomException(ErrorCode.ACCOUNT_SUSPENDED);
    }
  }

  private String accessToken(LoginUser user, Instant now) {
    var claims =
        JwtClaimsSet.builder()
            .issuer(props.issuer())
            .subject(user.userId().toString())
            .issuedAt(now)
            .expiresAt(now.plus(props.accessTokenTtl()))
            .claim(ROLE_CLAIM, user.role())
            .claim(NICKNAME_CLAIM, user.nickname() == null ? "" : user.nickname())
            .build();
    var header = JwsHeader.with(MacAlgorithm.HS256).build();
    return jwtEncoder.encode(JwtEncoderParameters.from(header, claims)).getTokenValue();
  }

  private String newRefreshToken(UUID userId, Instant now) {
    String raw = randomToken();
    refreshTokens.save(new RefreshToken(userId, hash(raw), now.plus(props.refreshTokenTtl()), now));
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
