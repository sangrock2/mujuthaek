package kr.mujuthaek.api.user.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;
import java.util.UUID;
import org.hibernate.annotations.UuidGenerator;

/** 로그인 유지용 refresh token. 원문은 쿠키에만 있고 여기엔 SHA-256 해시만 둬요. */
@Entity
@Table(schema = "account", name = "refresh_tokens")
public class RefreshToken {

  @Id
  @UuidGenerator(style = UuidGenerator.Style.VERSION_7)
  private UUID id;

  @Column(nullable = false)
  private UUID userId;

  @Column(nullable = false, length = 64, unique = true)
  private String tokenHash;

  @Column(nullable = false)
  private Instant expiresAt;

  @Column(nullable = false)
  private Instant createdAt;

  /** 로그인 연장으로 새 값으로 바꾼 시각. 바꾼 뒤 잠깐은 같은 값도 받아 줘요(AuthTokenService.ROTATED_GRACE). */
  private Instant rotatedAt;

  protected RefreshToken() {}

  public RefreshToken(UUID userId, String tokenHash, Instant expiresAt, Instant now) {
    this.userId = userId;
    this.tokenHash = tokenHash;
    this.expiresAt = expiresAt;
    this.createdAt = now;
  }

  public boolean expired(Instant now) {
    return !expiresAt.isAfter(now);
  }

  public UUID getUserId() {
    return userId;
  }

  public Instant getRotatedAt() {
    return rotatedAt;
  }
}
