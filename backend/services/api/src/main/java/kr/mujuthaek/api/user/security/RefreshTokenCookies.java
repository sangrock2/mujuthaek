package kr.mujuthaek.api.user.security;

import jakarta.servlet.http.Cookie;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.time.Duration;
import java.util.Arrays;
import java.util.Optional;
import kr.mujuthaek.api.user.service.JwtProperties;
import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseCookie;
import org.springframework.stereotype.Component;

/**
 * refresh token 쿠키. HttpOnly(자바스크립트로 못 읽음), SameSite=Lax(다른 사이트의 POST에는 안 실림),
 * Path=/api/auth(재발급·로그아웃 요청에만 실림), 운영은 Secure.
 */
@Component
public class RefreshTokenCookies {

  public static final String NAME = "refresh_token";
  private static final String PATH = "/api/auth";

  private final JwtProperties props;

  RefreshTokenCookies(JwtProperties props) {
    this.props = props;
  }

  public Optional<String> read(HttpServletRequest request) {
    return Optional.ofNullable(request.getCookies()).stream()
        .flatMap(Arrays::stream)
        .filter(c -> NAME.equals(c.getName()) && !c.getValue().isBlank())
        .map(Cookie::getValue)
        .findFirst();
  }

  public void write(HttpServletResponse response, String token, Duration maxAge) {
    response.addHeader(HttpHeaders.SET_COOKIE, cookie(token, maxAge).toString());
  }

  public void clear(HttpServletResponse response) {
    response.addHeader(HttpHeaders.SET_COOKIE, cookie("", Duration.ZERO).toString());
  }

  private ResponseCookie cookie(String value, Duration maxAge) {
    return ResponseCookie.from(NAME, value)
        .httpOnly(true)
        .secure(props.cookieSecure())
        .sameSite("Lax")
        .path(PATH)
        .maxAge(maxAge)
        .build();
  }
}
