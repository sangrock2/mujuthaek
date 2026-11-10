package kr.mujuthaek.api.user.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;
import java.util.UUID;
import org.hibernate.annotations.UuidGenerator;

/** 회원에 이어진 소셜 계정. (제공자, 제공자 회원번호)는 하나뿐이에요. */
@Entity
@Table(schema = "account", name = "social_accounts")
public class SocialAccount {

  @Id
  @UuidGenerator(style = UuidGenerator.Style.VERSION_7)
  private UUID id;

  @Column(nullable = false)
  private UUID userId;

  @Enumerated(EnumType.STRING)
  @Column(nullable = false, length = 20)
  private SocialProvider provider;

  @Column(nullable = false, length = 100)
  private String providerUserId;

  @Column(nullable = false)
  private Instant createdAt;

  protected SocialAccount() {}

  public SocialAccount(UUID userId, SocialProvider provider, String providerUserId, Instant now) {
    this.userId = userId;
    this.provider = provider;
    this.providerUserId = providerUserId;
    this.createdAt = now;
  }

  public UUID getUserId() {
    return userId;
  }

  public SocialProvider getProvider() {
    return provider;
  }

  public String getProviderUserId() {
    return providerUserId;
  }
}
