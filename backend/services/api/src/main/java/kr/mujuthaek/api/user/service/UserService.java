package kr.mujuthaek.api.user.service;

import java.util.UUID;
import kr.mujuthaek.api.common.exception.CustomException;
import kr.mujuthaek.api.common.exception.ErrorCode;
import kr.mujuthaek.api.user.domain.User;
import kr.mujuthaek.api.user.dto.response.MeResponse;
import kr.mujuthaek.api.user.repository.SocialAccountRepository;
import kr.mujuthaek.api.user.repository.UserRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** 회원 조회. */
@Service
@Transactional(readOnly = true)
public class UserService {

  private final UserRepository users;
  private final SocialAccountRepository socialAccounts;

  public UserService(UserRepository users, SocialAccountRepository socialAccounts) {
    this.users = users;
    this.socialAccounts = socialAccounts;
  }

  /** 회원이 아직 있는지 (탈퇴했으면 false). 탈퇴 뒤 남은 access token의 쓰기 요청을 막을 때 써요. */
  public boolean exists(UUID userId) {
    return users.existsById(userId);
  }

  public MeResponse getMe(UUID userId) {
    // 탈퇴했는데 남은 access token(최대 30분)으로 부른 경우: 401이라 프론트가 로그아웃 처리해요
    User user =
        users
            .findById(userId)
            .orElseThrow(
                () -> new CustomException(ErrorCode.UNAUTHENTICATED, "회원 정보가 없어요. 다시 로그인해 주세요"));
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
        user.getEmail());
  }
}
