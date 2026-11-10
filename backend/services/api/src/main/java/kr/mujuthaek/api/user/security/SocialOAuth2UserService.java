package kr.mujuthaek.api.user.security;

import jakarta.servlet.http.HttpServletRequest;
import java.util.Optional;
import kr.mujuthaek.api.common.exception.CustomException;
import kr.mujuthaek.api.user.service.SocialLoginService;
import kr.mujuthaek.api.user.service.SocialProfile;
import org.springframework.security.oauth2.client.userinfo.DefaultOAuth2UserService;
import org.springframework.security.oauth2.client.userinfo.OAuth2UserRequest;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.user.OAuth2User;
import org.springframework.stereotype.Component;
import org.springframework.web.context.request.RequestContextHolder;
import org.springframework.web.context.request.ServletRequestAttributes;

/** 소셜 로그인 성공 직후: 제공자 회원 정보를 받아 가입·로그인 처리하고, 이후에는 {@code LoginUser}만 써요. */
@Component
class SocialOAuth2UserService extends DefaultOAuth2UserService {

  /** 이번 로그인에서 처음 가입했으면 콜백 요청에 남기는 표시. LoginSuccessHandler가 읽어요 */
  static final String JOINED_ATTRIBUTE = SocialOAuth2UserService.class.getName() + ".joined";

  /** 제공자 응답에 회원번호가 없는 등 우리가 쓸 수 없는 응답. */
  static final String INVALID_SOCIAL_PROFILE = "invalid_social_profile";

  /** 가입·로그인 처리 중 우리 쪽 오류 (DB 등). */
  static final String SOCIAL_LOGIN_FAILED = "social_login_failed";

  private final SocialLoginService socialLoginService;

  SocialOAuth2UserService(SocialLoginService socialLoginService) {
    this.socialLoginService = socialLoginService;
  }

  @Override
  public OAuth2User loadUser(OAuth2UserRequest request) {
    OAuth2User provided = super.loadUser(request);
    String registrationId = request.getClientRegistration().getRegistrationId();
    Optional<String> withdrawTicket = currentRequest().flatMap(WithdrawalSession::ticket);
    if (withdrawTicket.isPresent()) { // 탈퇴 재인증: 가입·로그인하지 않고 탈퇴에 필요한 값만 넘겨요
      return toWithdrawalPrincipal(
          registrationId, provided, withdrawTicket.get(), request.getAccessToken().getTokenValue());
    }
    return toLoginUser(registrationId, provided);
  }

  OAuth2User toWithdrawalPrincipal(
      String registrationId, OAuth2User provided, String ticket, String providerAccessToken) {
    try {
      SocialProfile profile = SocialProfiles.from(registrationId, provided.getAttributes());
      return new WithdrawalPrincipal(
          profile.provider(), profile.providerUserId(), ticket, providerAccessToken);
    } catch (CustomException e) {
      throw failure(INVALID_SOCIAL_PROFILE, e);
    }
  }

  private static Optional<HttpServletRequest> currentRequest() {
    return RequestContextHolder.getRequestAttributes()
            instanceof ServletRequestAttributes attributes
        ? Optional.of(attributes.getRequest())
        : Optional.empty();
  }

  /**
   * 우리 예외는 스프링 시큐리티가 "로그인 실패"로 알아보지 못해서 그대로 두면 콜백 주소에서 500이 나요. OAuth2AuthenticationException으로 감싸야
   * LoginFailureHandler가 원인을 로그로 남기고 프론트 로그인 화면으로 돌려보내요.
   */
  OAuth2User toLoginUser(String registrationId, OAuth2User provided) {
    try {
      var login =
          socialLoginService.loginOrJoin(
              SocialProfiles.from(registrationId, provided.getAttributes()));
      if (login.joined()) {
        currentRequest().ifPresent(r -> r.setAttribute(JOINED_ATTRIBUTE, true));
      }
      return login.user();
    } catch (CustomException e) {
      throw failure(INVALID_SOCIAL_PROFILE, e);
    } catch (RuntimeException e) {
      throw failure(SOCIAL_LOGIN_FAILED, e);
    }
  }

  private static OAuth2AuthenticationException failure(String code, RuntimeException cause) {
    return new OAuth2AuthenticationException(
        new OAuth2Error(code, cause.getMessage(), null), cause.getMessage(), cause);
  }
}
