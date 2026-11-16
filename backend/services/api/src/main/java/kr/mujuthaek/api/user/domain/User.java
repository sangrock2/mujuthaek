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

/** 회원. 소득·자산·나이는 저장하지 않아요 (판정할 때만 받아요). */
@Entity
@Table(schema = "account", name = "users")
public class User {

  @Id
  @UuidGenerator(style = UuidGenerator.Style.VERSION_7)
  private UUID id;

  @Column(length = 50)
  private String nickname;

  @Enumerated(EnumType.STRING)
  @Column(nullable = false, length = 20)
  private Role role;

  @Column(nullable = false)
  private Instant createdAt;

  @Column(nullable = false)
  private Instant updatedAt;

  private Instant lastLoginAt;

  /** 계정 연락용 이메일 (선택). 주소·동의 버전·동의 시각은 같이 있거나 같이 비어요 */
  @Column(length = 254)
  private String email;

  @Column(length = 20)
  private String emailConsentVersion;

  private Instant emailConsentedAt;

  /** 가입 필수 동의(만 14세 이상 확인·이용약관·개인정보 수집·이용) 때 화면이 보여 준 약관 버전. 셋은 같이 있거나 같이 비어요 */
  @Column(length = 20)
  private String termsVersion;

  @Column(length = 20)
  private String privacyVersion;

  private Instant termsAgreedAt;

  protected User() {}

  private User(String nickname, Instant now) {
    this.nickname = nickname;
    this.role = Role.USER;
    this.createdAt = now;
    this.updatedAt = now;
    this.lastLoginAt = now;
  }

  /** 처음 소셜 로그인한 회원. 권한은 USER로 시작해요. */
  public static User join(String nickname, Instant now) {
    return new User(trim(nickname), now);
  }

  /** 로그인할 때마다: 닉네임은 소셜 계정에서 바뀌었으면 따라가고, 마지막 로그인 시각을 남겨요. */
  public void loggedIn(String nickname, Instant now) {
    if (nickname != null && !nickname.isBlank()) {
      this.nickname = trim(nickname);
    }
    this.lastLoginAt = now;
    this.updatedAt = now;
  }

  /** 가입 필수 동의를 남겨요 (다시 동의하면 버전·시각을 새로). 검사는 서비스에서 */
  public void agreeTerms(String termsVersion, String privacyVersion, Instant now) {
    this.termsVersion = termsVersion;
    this.privacyVersion = privacyVersion;
    this.termsAgreedAt = now;
    this.updatedAt = now;
  }

  public boolean termsAgreed() {
    return termsAgreedAt != null;
  }

  /** 닉네임 바꾸기 (실명일 수 있는 닉네임을 별칭으로 바꿀 때) */
  public void rename(String nickname, Instant now) {
    this.nickname = trim(nickname);
    this.updatedAt = now;
  }

  /** 저장할 때와 같은 방식으로 다듬은 닉네임 (앞뒤 공백, 50자) */
  public static String normalizedNickname(String nickname) {
    return trim(nickname);
  }

  /** 연락용 이메일 등록·변경. 동의한 문구 버전과 시각을 같이 남겨요 (검사는 서비스에서) */
  public void changeEmail(String email, String consentVersion, Instant now) {
    this.email = email;
    this.emailConsentVersion = consentVersion;
    this.emailConsentedAt = now;
    this.updatedAt = now;
  }

  /** 연락용 이메일 삭제 (동의 철회). 동의 기록도 같이 지워요 */
  public void removeEmail(Instant now) {
    this.email = null;
    this.emailConsentVersion = null;
    this.emailConsentedAt = null;
    this.updatedAt = now;
  }

  private static String trim(String nickname) {
    if (nickname == null) {
      return null;
    }
    String value = nickname.strip();
    return value.length() > 50 ? value.substring(0, 50) : value;
  }

  public UUID getId() {
    return id;
  }

  public String getNickname() {
    return nickname;
  }

  public Role getRole() {
    return role;
  }

  public Instant getCreatedAt() {
    return createdAt;
  }

  public Instant getLastLoginAt() {
    return lastLoginAt;
  }

  public String getEmail() {
    return email;
  }

  public String getEmailConsentVersion() {
    return emailConsentVersion;
  }

  public Instant getEmailConsentedAt() {
    return emailConsentedAt;
  }
}
