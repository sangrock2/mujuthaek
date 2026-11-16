package kr.mujuthaek.api.user.service;

import java.time.Clock;
import java.util.UUID;
import java.util.regex.Pattern;
import kr.mujuthaek.api.common.exception.CustomException;
import kr.mujuthaek.api.common.exception.ErrorCode;
import kr.mujuthaek.api.user.domain.User;
import kr.mujuthaek.api.user.repository.UserRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 가입 필수 동의(만 14세 이상 확인, 이용약관, 개인정보 수집·이용)를 서버에 남겨요. 예전에는 화면 상태로만 있어서 동의 화면을 건너뛰어도 회원 기능을 모두 쓸 수
 * 있었어요(2026-11-16 보안 감사 L-2). 동의 전에는 회원 기능이 403 TERMS_NOT_AGREED예요(SecurityConfig).
 */
@Service
public class TermsAgreementService {

  private static final Logger log = LoggerFactory.getLogger(TermsAgreementService.class);

  static final int MAX_VERSION_LENGTH = 20;
  private static final Pattern VERSION =
      Pattern.compile("^[A-Za-z0-9._-]{1," + MAX_VERSION_LENGTH + "}$");

  private final UserRepository users;
  private final Clock clock;

  public TermsAgreementService(UserRepository users, Clock clock) {
    this.users = users;
    this.clock = clock;
  }

  /** 동의를 남겨요. 다시 보내면 버전·시각을 새로 남겨요 */
  @Transactional
  public void agree(UUID userId, String termsVersion, String privacyVersion, Boolean ageOver14) {
    if (!Boolean.TRUE.equals(ageOver14)) {
      throw new CustomException(ErrorCode.VALIDATION_FAILED, "ageOver14: 만 14세 이상이어야 가입할 수 있어요");
    }
    String terms = version("termsVersion", termsVersion);
    String privacy = version("privacyVersion", privacyVersion);
    User user =
        users
            .findById(userId)
            .orElseThrow(
                () -> new CustomException(ErrorCode.UNAUTHENTICATED, "회원 정보가 없어요. 다시 로그인해 주세요"));
    user.agreeTerms(terms, privacy, clock.instant());
    log.info("가입 필수 동의: userId={}, 약관={}, 처리방침={}", userId, terms, privacy);
  }

  private static String version(String field, String value) {
    String v = value == null ? "" : value.strip();
    if (!VERSION.matcher(v).matches()) {
      throw new CustomException(
          ErrorCode.VALIDATION_FAILED, field + ": 영문·숫자·점·하이픈으로 " + MAX_VERSION_LENGTH + "자까지예요");
    }
    return v;
  }
}
