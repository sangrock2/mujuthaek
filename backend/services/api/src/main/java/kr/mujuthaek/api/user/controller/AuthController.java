package kr.mujuthaek.api.user.controller;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import kr.mujuthaek.api.common.exception.CustomException;
import kr.mujuthaek.api.common.exception.ErrorCode;
import kr.mujuthaek.api.user.controller.spec.AuthApiSpec;
import kr.mujuthaek.api.user.dto.response.TokenResponse;
import kr.mujuthaek.api.user.security.RefreshTokenCookies;
import kr.mujuthaek.api.user.service.AuthTokenService;
import kr.mujuthaek.api.user.service.TokenPair;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** access token 재발급·로그아웃 (설명은 {@link AuthApiSpec}). */
@RestController
@RequestMapping("/api/auth")
class AuthController implements AuthApiSpec {

  private final AuthTokenService tokens;
  private final RefreshTokenCookies cookies;

  AuthController(AuthTokenService tokens, RefreshTokenCookies cookies) {
    this.tokens = tokens;
    this.cookies = cookies;
  }

  @Override
  @PostMapping("/refresh")
  public TokenResponse refresh(HttpServletRequest request, HttpServletResponse response) {
    String raw =
        cookies
            .read(request)
            .orElseThrow(() -> new CustomException(ErrorCode.INVALID_REFRESH_TOKEN));
    TokenPair pair;
    try {
      pair = tokens.refresh(raw);
    } catch (CustomException e) {
      // 쿠키가 없어졌거나 만료됐을 때만 지워요(정지 등 다른 오류로 지우면 먼저 온 요청이 받은 새 쿠키까지 지워져요).
      // 바꾼 지 얼마 안 된 옛 쿠키는 401이 아니라 새 토큰을 받아요(AuthTokenService.ROTATED_GRACE)
      if (e.errorCode() == ErrorCode.INVALID_REFRESH_TOKEN) {
        cookies.clear(response);
      }
      throw e;
    }
    cookies.write(response, pair.refreshToken(), pair.refreshTokenTtl());
    return new TokenResponse(pair.accessToken(), "Bearer", pair.accessTokenTtl().toSeconds());
  }

  @Override
  @PostMapping("/logout")
  public ResponseEntity<Void> logout(HttpServletRequest request, HttpServletResponse response) {
    cookies.read(request).ifPresent(tokens::revoke);
    cookies.clear(response);
    return ResponseEntity.noContent().build();
  }
}
