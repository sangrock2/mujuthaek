package kr.mujuthaek.api.user.security;

import static kr.mujuthaek.api.user.domain.AdminPermission.ACTIVITY;
import static kr.mujuthaek.api.user.domain.AdminPermission.ADMIN_APPOINT;
import static kr.mujuthaek.api.user.domain.AdminPermission.BENEFIT_REVIEW;
import static kr.mujuthaek.api.user.domain.AdminPermission.CHAT;
import static kr.mujuthaek.api.user.domain.AdminPermission.CRITERIA;
import static kr.mujuthaek.api.user.domain.AdminPermission.NOTICE_REVIEW;
import static kr.mujuthaek.api.user.domain.AdminPermission.PERMISSION_GRANT;
import static kr.mujuthaek.api.user.domain.AdminPermission.PERMISSION_REVOKE;
import static kr.mujuthaek.api.user.domain.AdminPermission.REPORTS;
import static kr.mujuthaek.api.user.domain.AdminPermission.SOURCES;
import static kr.mujuthaek.api.user.domain.AdminPermission.TRAFFIC;
import static kr.mujuthaek.api.user.domain.AdminPermission.USERS_SUSPEND;
import static kr.mujuthaek.api.user.domain.AdminPermission.USERS_VIEW;

import java.util.List;
import kr.mujuthaek.api.common.exception.ErrorCode;
import kr.mujuthaek.api.user.domain.AdminPermission;
import kr.mujuthaek.api.user.service.AdminUserService;
import kr.mujuthaek.api.user.service.JwtProperties;
import kr.mujuthaek.api.user.service.UserService;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AuthorizeHttpRequestsConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.oauth2.client.web.HttpSessionOAuth2AuthorizedClientRepository;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository;
import org.springframework.security.oauth2.server.resource.web.BearerTokenResolver;
import org.springframework.security.oauth2.server.resource.web.DefaultBearerTokenResolver;
import org.springframework.security.oauth2.server.resource.web.authentication.BearerTokenAuthenticationFilter;
import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.AccessDeniedHandler;
import org.springframework.security.web.servlet.util.matcher.PathPatternRequestMatcher;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;
import org.springframework.web.util.UrlPathHelper;

/**
 * 로그인·권한 규칙 (JWT).
 *
 * <ul>
 *   <li>로그인: {@code GET /oauth2/authorization/kakao} → 카카오 → {@code /login/oauth2/code/kakao} →
 *       refresh token 쿠키를 받고 프론트로 돌아가요 (LoginSuccessHandler)
 *   <li>access token: {@code POST /api/auth/refresh}로 받아 {@code Authorization: Bearer}로 보내요
 *   <li>{@code /api/admin/**}는 관리자, 경로마다 받은 권한이 있어야 해요({@link #adminPaths}). {@code /api/users/**}는
 *       로그인한 회원만. 나머지(공고·혜택 조회 등)는 누구나
 *   <li>서버는 로그인 상태를 저장하지 않아요(STATELESS). 카카오 로그인 중간의 state만 잠깐 세션에 둬요
 *   <li>CSRF는 끄요: 인증은 Bearer 헤더라 다른 사이트가 대신 보낼 수 없고, 쿠키를 쓰는 재발급·로그아웃은 SameSite=Lax + POST라 다른 사이트에서
 *       실리지 않아요
 * </ul>
 */
@Configuration
@EnableConfigurationProperties({LoginProperties.class, JwtProperties.class})
class SecurityConfig {

  @Bean
  SecurityFilterChain securityFilterChain(
      HttpSecurity http,
      SocialOAuth2UserService socialUserService,
      LoginSuccessHandler loginSuccessHandler,
      LoginFailureHandler loginFailureHandler,
      LoginUserJwtConverter jwtConverter,
      KnownProviderAuthorizationRequestResolver providerResolver,
      ProblemResponses problems,
      UserService userService,
      AdminUserService adminUsers,
      AdminAuthorization admin)
      throws Exception {
    AuthenticationEntryPoint unauthorized =
        (request, response, error) -> problems.write(request, response, ErrorCode.UNAUTHENTICATED);
    AccessDeniedHandler forbidden =
        (request, response, error) -> problems.write(request, response, ErrorCode.FORBIDDEN);
    http.cors(Customizer.withDefaults())
        .csrf(csrf -> csrf.disable())
        .sessionManagement(
            session -> session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
        .logout(logout -> logout.disable()) // 로그아웃은 AuthController (refresh token 폐기)
        .authorizeHttpRequests(
            auth ->
                adminPaths(auth, admin)
                    .requestMatchers("/api/users/**")
                    .authenticated()
                    .anyRequest()
                    .permitAll())
        .oauth2Login(
            login ->
                login
                    .authorizationEndpoint(
                        start -> start.authorizationRequestResolver(providerResolver))
                    .userInfoEndpoint(info -> info.userService(socialUserService))
                    .successHandler(loginSuccessHandler)
                    .failureHandler(loginFailureHandler))
        .oauth2ResourceServer(
            server ->
                server
                    .bearerTokenResolver(bearerTokenResolver())
                    .jwt(jwt -> jwt.jwtAuthenticationConverter(jwtConverter))
                    .authenticationEntryPoint(unauthorized)
                    .accessDeniedHandler(forbidden))
        .addFilterAfter(
            new WithdrawnUserFilter(userService, adminUsers, problems),
            BearerTokenAuthenticationFilter.class)
        .exceptionHandling(
            errors ->
                errors
                    .defaultAuthenticationEntryPointFor(
                        unauthorized, PathPatternRequestMatcher.withDefaults().matcher("/api/**"))
                    .accessDeniedHandler(forbidden));
    return http.build();
  }

  /**
   * 관리자 화면 경로와 필요한 권한 (권한 목록은 {@link AdminPermission}). 여기에 없는 새 관리자 경로는 최상위만 열려요 — 새 화면을 만들면 여기에
   * 권한을 정해 주세요. 회원 관리의 주고 빼는 규칙은 AdminUserService가 다시 봐요.
   */
  private static AuthorizeHttpRequestsConfigurer<HttpSecurity>
          .AuthorizationManagerRequestMatcherRegistry
      adminPaths(
          AuthorizeHttpRequestsConfigurer<HttpSecurity>.AuthorizationManagerRequestMatcherRegistry
              auth,
          AdminAuthorization admin) {
    return auth.requestMatchers("/api/admin/me")
        .access(admin.admin())
        .requestMatchers(HttpMethod.GET, "/api/admin/users/names")
        .access(admin.active())
        .requestMatchers("/api/admin/super/**")
        .access(admin.superOnly())
        .requestMatchers("/api/admin/users/*/role")
        .access(admin.anyOf(ADMIN_APPOINT))
        .requestMatchers("/api/admin/users/*/permissions")
        .access(admin.anyOf(PERMISSION_GRANT, PERMISSION_REVOKE))
        .requestMatchers("/api/admin/users/*/suspension")
        .access(admin.anyOf(USERS_SUSPEND))
        .requestMatchers(HttpMethod.GET, "/api/admin/users/changes")
        .access(
            admin.anyOf(
                ACTIVITY, ADMIN_APPOINT, PERMISSION_GRANT, PERMISSION_REVOKE, USERS_SUSPEND))
        .requestMatchers(HttpMethod.GET, "/api/admin/users")
        .access(
            admin.anyOf(
                USERS_VIEW, ADMIN_APPOINT, PERMISSION_GRANT, PERMISSION_REVOKE, USERS_SUSPEND))
        // 검수 대기열은 공고·혜택을 섞어요. 보낸 kinds마다 그 검수 권한을 봐요(아래 /api/admin/reviews/** 보다 먼저)
        .requestMatchers(HttpMethod.GET, "/api/admin/reviews/queue")
        .access(admin.reviewQueue())
        .requestMatchers("/api/admin/reviews/**")
        .access(admin.anyOf(NOTICE_REVIEW))
        .requestMatchers("/api/admin/benefit-reviews/**")
        .access(admin.anyOf(BENEFIT_REVIEW))
        .requestMatchers("/api/admin/sources/**")
        .access(admin.anyOf(SOURCES))
        .requestMatchers(HttpMethod.GET, "/api/admin/criteria/*/history")
        .access(admin.anyOf(CRITERIA, ACTIVITY))
        .requestMatchers("/api/admin/criteria/**", "/api/admin/regulated-areas/**")
        .access(admin.anyOf(CRITERIA))
        .requestMatchers(
            "/api/admin/reports/**",
            "/api/admin/area-reports/**",
            "/api/admin/policy-duplicates/**")
        .access(admin.anyOf(REPORTS))
        .requestMatchers("/api/admin/chat/**")
        .access(admin.anyOf(CHAT))
        .requestMatchers("/api/admin/traffic/**", "/api/admin/notifications/**")
        .access(admin.anyOf(TRAFFIC))
        .requestMatchers("/api/admin/activity/**")
        .access(admin.anyOf(ACTIVITY))
        .requestMatchers("/api/admin/**")
        .access(admin.superOnly());
  }

  /**
   * {@code Authorization: Bearer}를 읽는 곳. 재발급·로그아웃({@code /api/auth/**})은 쿠키로만 확인해서 헤더를 읽지 않아요. 프론트가
   * 만료된 access token을 붙여 보내도 재발급이 401로 막히지 않게요 (헤더가 있으면 필터가 permitAll보다 먼저 검증해서 401을 내요).
   */
  static BearerTokenResolver bearerTokenResolver() {
    var bearer = new DefaultBearerTokenResolver();
    // 경로는 앱 안 경로로 봐요(요청 기록 필터와 같음). 전달 헤더(X-Forwarded-Prefix)가 바꾼 요청 주소로 보면 토큰을 무시하게 만들 수 있었어요(재검토)
    return request ->
        UrlPathHelper.rawPathInstance.getPathWithinApplication(request).startsWith("/api/auth/")
            ? null
            : bearer.resolve(request);
  }

  /**
   * 로그인할 때 받은 제공자 토큰(카카오·네이버·구글 access token)을 보관하는 곳. 스프링 기본값은 서버 메모리에 회원마다 계속 쌓아 둬요. 우리는 제공자 API를
   * 다시 부르지 않으니 로그인 중간 세션에만 두고, 로그인이 끝나면 세션과 함께 지워요.
   */
  @Bean
  OAuth2AuthorizedClientRepository authorizedClientRepository() {
    return new HttpSessionOAuth2AuthorizedClientRepository();
  }

  /**
   * 프론트(다른 포트·도메인)에서 쿠키(refresh token)와 Authorization 헤더를 실어 부를 수 있게 프론트 주소만 허용해요. frontendUrl과
   * corsOrigins(쉼표로 여러 개)만 허용해요. Last-Event-ID는 채팅 SSE가 끊겼다 다시 붙을 때 브라우저가 실어 보내는 헤더예요 (허용하지 않으면 다른
   * 도메인에서 재연결이 막혀요).
   */
  @Bean
  CorsConfigurationSource corsConfigurationSource(LoginProperties props) {
    var config = new CorsConfiguration();
    config.setAllowedOrigins(props.allowedOrigins());
    config.setAllowedMethods(List.of("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"));
    config.setAllowedHeaders(List.of("Content-Type", "Authorization", "Last-Event-ID"));
    config.setAllowCredentials(true);
    var source = new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/**", config);
    return source;
  }
}
