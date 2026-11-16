package kr.mujuthaek.api.user;

import kr.mujuthaek.api.user.service.LoginUser;
import kr.mujuthaek.api.user.service.TermsAgreementService;

/**
 * 시험 회원을 가입 필수 동의까지 마친 상태로 만들어요. 동의 전에는 회원 기능(내 정보 아래 대부분, 채팅 쓰기, 제보)이 403
 * TERMS_NOT_AGREED라서(2026-11-16 보안 감사 L-2), 회원 기능을 시험하는 곳은 로그인한 뒤 이걸 거쳐요.
 */
public final class TermsFixture {

  private TermsFixture() {}

  public static LoginUser agreed(TermsAgreementService terms, LoginUser user) {
    terms.agree(user.userId(), "1.0", "1.0", true);
    return user;
  }
}
