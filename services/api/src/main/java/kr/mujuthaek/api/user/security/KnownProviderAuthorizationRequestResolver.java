package kr.mujuthaek.api.user.security;

import jakarta.servlet.http.HttpServletRequest;
import java.util.Map;
import java.util.regex.Pattern;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.DefaultOAuth2AuthorizationRequestResolver;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizationRequestResolver;
import org.springframework.security.oauth2.core.endpoint.OAuth2AuthorizationRequest;
import org.springframework.security.web.servlet.util.matcher.PathPatternRequestMatcher;
import org.springframework.security.web.util.matcher.RequestMatcher;
import org.springframework.stereotype.Component;

/**
 * 로그인 시작({@code /oauth2/authorization/{제공자}})에서 등록되지 않은 제공자(예: facebook)는 로그인 요청으로 보지 않아요.
 *
 * <p>기본 처리기는 이 경우 예외를 던져서 500 + 긴 스택 트레이스 경고 로그가 남아요(봇·잘못된 링크가 부르면 로그가 쌓여요). 여기서는 null을 돌려 필터가 그냥
 * 넘기게 하고, 컨트롤러가 없으니 404 NOT_FOUND(Problem Details)가 돼요.
 */
@Component
class KnownProviderAuthorizationRequestResolver implements OAuth2AuthorizationRequestResolver {

  static final String BASE_URI =
      DefaultOAuth2AuthorizationRequestResolver.DEFAULT_AUTHORIZATION_REQUEST_BASE_URI;

  /** 탈퇴 티켓 모양: 무작위 32바이트를 패딩 없는 URL Base64로 (AuthTokenService.randomToken, 43자). */
  private static final Pattern TICKET = Pattern.compile("[A-Za-z0-9_-]{43}");

  private final ClientRegistrationRepository registrations;
  private final DefaultOAuth2AuthorizationRequestResolver delegate;
  private final RequestMatcher loginStart =
      PathPatternRequestMatcher.withDefaults().matcher(BASE_URI + "/{registrationId}");

  KnownProviderAuthorizationRequestResolver(ClientRegistrationRepository registrations) {
    this.registrations = registrations;
    this.delegate = new DefaultOAuth2AuthorizationRequestResolver(registrations, BASE_URI);
  }

  @Override
  public OAuth2AuthorizationRequest resolve(HttpServletRequest request) {
    var match = loginStart.matcher(request);
    if (!match.isMatch()) {
      return delegate.resolve(request);
    }
    String registrationId = match.getVariables().get("registrationId");
    if (!known(registrationId)) {
      return null;
    }
    String ticket = request.getParameter(WithdrawalSession.PARAM);
    if (ticket != null && !ticket.isBlank() && !TICKET.matcher(ticket).matches()) {
      // 발급한 티켓 모양이 아니면 세션을 만들지 않고 404예요. 인증 없이 부르는 주소라, 예전엔 길이 검사 없이 세션에 넣어
      // 폼 본문(2MB까지)으로 큰 값을 되풀이해 세션 메모리를 채울 수 있었어요(2026-11-10 코드 검토)
      return null;
    }
    OAuth2AuthorizationRequest authorization = delegate.resolve(request);
    if (authorization == null || ticket == null || ticket.isBlank()) {
      WithdrawalSession.clear(request);
      return authorization;
    }
    WithdrawalSession.start(request, ticket);
    return reauthenticate(authorization, registrationId);
  }

  /** 탈퇴는 본인 확인이라, 이미 소셜에 로그인돼 있어도 다시 로그인(계정 선택)하게 해요. */
  static OAuth2AuthorizationRequest reauthenticate(
      OAuth2AuthorizationRequest authorization, String registrationId) {
    Map<String, Object> extra =
        switch (registrationId) {
          case "kakao" -> Map.of("prompt", "login");
          case "naver" -> Map.of("auth_type", "reauthenticate");
          case "google" -> Map.of("prompt", "select_account");
          default -> Map.of();
        };
    return OAuth2AuthorizationRequest.from(authorization)
        .additionalParameters(params -> params.putAll(extra))
        .build();
  }

  @Override
  public OAuth2AuthorizationRequest resolve(HttpServletRequest request, String registrationId) {
    return known(registrationId) ? delegate.resolve(request, registrationId) : null;
  }

  private boolean known(String registrationId) {
    return registrationId != null && registrations.findByRegistrationId(registrationId) != null;
  }
}
