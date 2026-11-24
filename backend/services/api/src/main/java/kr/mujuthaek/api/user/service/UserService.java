package kr.mujuthaek.api.user.service;

import java.time.Clock;
import java.util.UUID;
import java.util.regex.Pattern;
import kr.mujuthaek.api.common.exception.CustomException;
import kr.mujuthaek.api.common.exception.ErrorCode;
import kr.mujuthaek.api.user.domain.User;
import kr.mujuthaek.api.user.dto.response.MeResponse;
import kr.mujuthaek.api.user.repository.SocialAccountRepository;
import kr.mujuthaek.api.user.repository.UserRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** 회원 조회 및 프로필 관리. */
@Service
@Transactional(readOnly = true)
public class UserService {

  private static final int MAX_NICKNAME = 24;
  private static final Pattern UNSAFE_NICKNAME =
      Pattern.compile(
          "[\\p{Cc}\\p{Cs}\\p{Zl}\\p{Zp}\\x{061C}\\x{200E}\\x{200F}\\x{202A}-\\x{202E}\\x{2066}-\\x{2069}]");

  private final UserRepository users;
  private final SocialAccountRepository socialAccounts;
  private final Clock clock;

  public UserService(UserRepository users, SocialAccountRepository socialAccounts, Clock clock) {
    this.users = users;
    this.socialAccounts = socialAccounts;
    this.clock = clock;
  }

  /** 회원이 아직 있는지 (탈퇴했으면 false). 탈퇴 뒤 남은 access token의 쓰기 요청을 막을 때 써요. */
  public boolean exists(UUID userId) {
    return users.existsById(userId);
  }

  public MeResponse getMe(UUID userId) {
    // 탈퇴했는데 남은 access token(최대 30분)으로 부른 경우: 401이라 프론트가 로그아웃 처리해요
    User user = users.findById(userId).orElseThrow(UserService::missingMember);
    var providers =
        socialAccounts.findByUserIdOrderByCreatedAt(userId).stream()
            .map(a -> a.getProvider().name())
            .toList();
    return new MeResponse(
        user.getId(),
        user.getNickname(),
        user.getRole().name(),
        providers,
        user.getCreatedAt(),
        user.getEmail(),
        user.termsAgreed());
  }

  @Transactional
  public String changeNickname(UUID userId, String input) {
    String nickname = input == null ? "" : input.replaceAll("(?U)^\\s+|\\s+$", "");
    int length = nickname.codePointCount(0, nickname.length());
    if (length < 2 || length > MAX_NICKNAME || UNSAFE_NICKNAME.matcher(nickname).find()) {
      throw new CustomException(ErrorCode.VALIDATION_FAILED, "닉네임을 2~24자로 입력해 주세요.");
    }
    User user = users.lockById(userId).orElseThrow(UserService::missingMember);
    user.chooseNickname(nickname, clock.instant());
    return user.getNickname();
  }

  public String getNickname(UUID userId) {
    return users.findById(userId).orElseThrow(UserService::missingMember).getNickname();
  }

  private static CustomException missingMember() {
    return new CustomException(ErrorCode.UNAUTHENTICATED, "회원 정보가 없어요. 다시 로그인해 주세요");
  }

  /** 가입 필수 동의를 했는지. 없는 회원이면 false (요청마다 회원 기능 앞에서 봐요) */
  public boolean termsAgreed(UUID userId) {
    return users.termsAgreed(userId);
  }
}
