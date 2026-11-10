package kr.mujuthaek.api.user.service;

import java.time.Clock;
import java.util.Locale;
import java.util.UUID;
import java.util.regex.Pattern;
import kr.mujuthaek.api.common.exception.CustomException;
import kr.mujuthaek.api.common.exception.ErrorCode;
import kr.mujuthaek.api.user.domain.User;
import kr.mujuthaek.api.user.repository.UserRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 계정 연락용 이메일 (선택). 약관·개인정보처리방침 변경, 이용 제한, 계정 안내처럼 꼭 알려야 할 때만 쓰고 알림 메일·광고는 보내지 않아요. 가입 마무리 화면과
 * 마이페이지가 같은 API로 등록·변경하고, 지우면 동의 철회예요. 인증 코드는 받지 않아요. 한 주소는 한 회원만 써요(대소문자 무시, 다른 회원이 쓰면 409
 * EMAIL_ALREADY_USED).
 *
 * <p>주소는 로그·오류 문구에 넣지 않아요 (회원 ID만).
 */
@Service
public class ContactEmailService {

  private static final Logger log = LoggerFactory.getLogger(ContactEmailService.class);

  /** RFC 5321 주소 최대 길이 */
  static final int MAX_EMAIL_LENGTH = 254;

  static final int MAX_CONSENT_VERSION_LENGTH = 20;

  /**
   * 아이디@도메인.최상위. 공백(전각 공백 같은 유니코드 공백 포함)·@ 두 개·제어 문자는 안 돼요 (보내 보기 전에는 진짜 주소인지 알 수 없어서 모양만 봐요). 제어
   * 문자 중 NUL은 DB가 받지 않아 500이 나고, 줄바꿈은 나중에 메일 헤더에 넣을 때 위험해요
   */
  private static final Pattern EMAIL =
      Pattern.compile(
          "^[^\\s\\p{Z}@\\p{Cc}]{1,64}@[^\\s\\p{Z}@.\\p{Cc}]+(\\.[^\\s\\p{Z}@.\\p{Cc}]+)+$");

  private static final Pattern CONSENT_VERSION = Pattern.compile("^[A-Za-z0-9._-]+$");

  private final UserRepository users;
  private final Clock clock;

  public ContactEmailService(UserRepository users, Clock clock) {
    this.users = users;
    this.clock = clock;
  }

  /** 등록·변경. 같은 주소로 다시 보내도 동의 버전·시각을 새로 남겨요. 다른 회원이 쓰는 주소면 409 */
  @Transactional
  public void change(UUID userId, String email, String consentVersion) {
    String address = normalize(email);
    String version = checkConsentVersion(consentVersion);
    User user = user(userId);
    boolean first = user.getEmail() == null;
    if (users.emailUsedByOther(address, userId)) {
      throw new CustomException(ErrorCode.EMAIL_ALREADY_USED);
    }
    user.changeEmail(address, version, clock.instant());
    try {
      users.flush(); // 동시에 같은 주소를 넣으면 유니크 인덱스가 막아요 → 500이 아니라 409
    } catch (DataIntegrityViolationException e) {
      throw new CustomException(ErrorCode.EMAIL_ALREADY_USED);
    }
    log.info("연락용 이메일 {}: userId={}, 동의 버전={}", first ? "등록" : "변경", userId, version);
  }

  /** 삭제 (동의 철회). 없어도 조용히 끝나요 */
  @Transactional
  public void remove(UUID userId) {
    User user = user(userId);
    if (user.getEmail() != null) {
      user.removeEmail(clock.instant());
      log.info("연락용 이메일 삭제: userId={}", userId);
    }
  }

  /** 앞뒤 공백을 빼고, 도메인은 소문자로 (아이디 부분은 대소문자를 구분하는 메일 서버가 있어 그대로) */
  static String normalize(String email) {
    if (email == null || email.isBlank()) {
      throw invalid("email", "꼭 있어야 해요");
    }
    String value = email.strip();
    if (value.length() > MAX_EMAIL_LENGTH) {
      throw invalid("email", MAX_EMAIL_LENGTH + "자를 넘어요");
    }
    if (!EMAIL.matcher(value).matches()) {
      throw invalid("email", "이메일 주소 형식이 아니에요");
    }
    int at = value.lastIndexOf('@');
    return value.substring(0, at + 1) + value.substring(at + 1).toLowerCase(Locale.ROOT);
  }

  private static String checkConsentVersion(String consentVersion) {
    if (consentVersion == null || consentVersion.isBlank()) {
      throw invalid("consentVersion", "꼭 있어야 해요");
    }
    String value = consentVersion.strip();
    if (value.length() > MAX_CONSENT_VERSION_LENGTH || !CONSENT_VERSION.matcher(value).matches()) {
      throw invalid("consentVersion", "영문·숫자·점·하이픈으로 " + MAX_CONSENT_VERSION_LENGTH + "자까지예요");
    }
    return value;
  }

  private User user(UUID userId) {
    // 탈퇴했는데 남은 access token으로 부른 경우 (쓰기 요청은 필터가 먼저 막지만 한 번 더)
    return users
        .findById(userId)
        .orElseThrow(
            () -> new CustomException(ErrorCode.UNAUTHENTICATED, "회원 정보가 없어요. 다시 로그인해 주세요"));
  }

  /** 오류 문구에는 칸 이름만 넣고 값은 넣지 않아요 */
  private static CustomException invalid(String field, String reason) {
    return new CustomException(ErrorCode.VALIDATION_FAILED, field + ": " + reason);
  }
}
