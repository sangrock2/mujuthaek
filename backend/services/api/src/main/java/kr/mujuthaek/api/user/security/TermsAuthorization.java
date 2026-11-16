package kr.mujuthaek.api.user.security;

import kr.mujuthaek.api.user.service.LoginUser;
import kr.mujuthaek.api.user.service.UserService;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationDeniedException;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;
import org.springframework.stereotype.Component;

/**
 * 회원 기능 앞의 가입 필수 동의 확인. 요청마다 DB의 지금 상태를 봐요(동의한 뒤 토큰을 다시 받지 않아도 바로 열려요).
 *
 * <p>예전에는 동의가 화면 상태로만 있어서, 동의 화면을 건너뛰어도 찜·준비함·채팅·제보·푸시를 모두 쓸 수 있었어요(2026-11-16 보안 감사 L-2). 로그인하지
 * 않았으면 거절만 하고(그러면 401), 로그인했는데 동의하지 않았으면 {@link NotAgreed}로 거절해 403 TERMS_NOT_AGREED가 나가요.
 */
@Component
class TermsAuthorization {

  private final UserService users;

  TermsAuthorization(UserService users) {
    this.users = users;
  }

  /** 로그인했고 가입 필수 동의를 했으면 */
  AuthorizationManager<RequestAuthorizationContext> agreed() {
    return (authentication, context) -> {
      var auth = authentication.get();
      if (auth == null || !(auth.getPrincipal() instanceof LoginUser user)) {
        return new AuthorizationDecision(false);
      }
      return users.termsAgreed(user.userId()) ? new AuthorizationDecision(true) : new NotAgreed();
    };
  }

  /** 접근 거절이 동의하지 않아서인지 (그러면 403 TERMS_NOT_AGREED) */
  static boolean notAgreed(AccessDeniedException error) {
    return error instanceof AuthorizationDeniedException denied
        && denied.getAuthorizationResult() instanceof NotAgreed;
  }

  /** 로그인했지만 가입 필수 동의를 하지 않아 거절 */
  static final class NotAgreed extends AuthorizationDecision {
    NotAgreed() {
      super(false);
    }
  }
}
