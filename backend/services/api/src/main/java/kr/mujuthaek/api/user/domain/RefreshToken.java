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

  @Column(nullable = false)
  private UUID familyId;

  @Column(nullable = false, length = 64, unique = true)
  private String tokenHash;

  @Column(nullable = false)
  private Instant expiresAt;

  @Column(nullable = false)
  private Instant createdAt;

  /** 이 로그인 계보의 소셜 인증 시각. refresh 회전으로 갱신하지 않아요. */
  @Column(nullable = false)
  private Instant authenticatedAt;

  /** 로그인 연장으로 사용한 시각. 같은 값이 다시 오면 계보 전체를 폐기해요. */
  private Instant rotatedAt;

  protected RefreshToken() {}

  public RefreshToken(UUID userId, String tokenHash, Instant expiresAt, Instant now) {
    this(userId, UUID.randomUUID(), tokenHash, expiresAt, now);
  }

  public RefreshToken(
      UUID userId, UUID familyId, String tokenHash, Instant expiresAt, Instant now) {
    this(userId, familyId, tokenHash, expiresAt, now, now);
  }

  public RefreshToken(
      UUID userId,
      UUID familyId,
      String tokenHash,
      Instant expiresAt,
      Instant now,
      Instant authenticatedAt) {
    this.userId = userId;
    this.familyId = familyId;
    this.tokenHash = tokenHash;
    this.expiresAt = expiresAt;
    this.createdAt = now;
    this.authenticatedAt = authenticatedAt;
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

  public UUID getFamilyId() {
    return familyId;
  }

  public Instant getAuthenticatedAt() {
    return authenticatedAt;
  }
}
