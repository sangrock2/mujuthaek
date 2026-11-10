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

/** 탈퇴 재인증 티켓. 원문은 재인증 주소에만 있고 여기엔 해시만 둬요. 일회용. */
@Entity
@Table(schema = "account", name = "withdrawal_tickets")
public class WithdrawalTicket {

  @Id
  @UuidGenerator(style = UuidGenerator.Style.VERSION_7)
  private UUID id;

  @Column(nullable = false)
  private UUID userId;

  @Enumerated(EnumType.STRING)
  @Column(nullable = false, length = 20)
  private SocialProvider provider;

  @Column(nullable = false, length = 64, unique = true)
  private String ticketHash;

  @Column(nullable = false)
  private Instant expiresAt;

  @Column(nullable = false)
  private Instant createdAt;

  protected WithdrawalTicket() {}

  public WithdrawalTicket(
      UUID userId, SocialProvider provider, String ticketHash, Instant expiresAt, Instant now) {
    this.userId = userId;
    this.provider = provider;
    this.ticketHash = ticketHash;
    this.expiresAt = expiresAt;
    this.createdAt = now;
  }

  public boolean expired(Instant now) {
    return !expiresAt.isAfter(now);
  }

  public UUID getUserId() {
    return userId;
  }

  public SocialProvider getProvider() {
    return provider;
  }
}
