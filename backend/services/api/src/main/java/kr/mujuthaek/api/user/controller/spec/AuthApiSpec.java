package kr.mujuthaek.api.user.controller.spec;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import kr.mujuthaek.api.user.dto.response.TokenResponse;
import org.springframework.http.ResponseEntity;

@Tag(
    name = "로그인 토큰",
    description =
        "refresh token 쿠키로 access token을 받고 로그아웃해요. 로그인 없이 부르고 Authorization 헤더는 읽지 않아요. "
            + "소셜 로그인은 브라우저에서 /oauth2/authorization/{kakao|naver|google}로 시작해요(스프링 시큐리티라 여기 없어요). "
            + "끝나면 refresh token 쿠키를 받고 프론트 /auth/callback으로 돌아와요(처음 가입이면 ?new=1). "
            + "실패하면 프론트 /login?error=social&reason=<이유>로 돌아와요(이용 정지는 reason=suspended).")
public interface AuthApiSpec {

  @Operation(
      summary = "access token 발급·재발급",
      description =
          "브라우저가 실어 보낸 refresh token 쿠키(refresh_token, HttpOnly, Path=/api/auth)로 확인해요. "
              + "refresh token도 새 값으로 바꿔 쿠키에 다시 넣어요. "
              + "바꾼 지 30초 안의 옛 쿠키로 와도 새 토큰을 줘요(탭 여러 개가 함께 연장할 때). "
              + "access token의 권한·닉네임은 지금 회원 정보로 채워요(권한이 바뀌면 다음 재발급부터 적용).")
  @ApiResponse(
      responseCode = "200",
      description = "access token (tokenType은 Bearer, expiresIn은 남은 초). 새 refresh token은 쿠키로 와요")
  @ApiResponse(
      responseCode = "401",
      description =
          "INVALID_REFRESH_TOKEN — 쿠키가 없거나 만료·폐기됐어요(바꾼 지 30초가 지난 옛 쿠키 포함). 쿠키를 지우니 다시 로그인해요")
  @ApiResponse(
      responseCode = "403",
      description =
          "ACCOUNT_SUSPENDED — 이용이 정지된 계정이에요. 정지하면 refresh token을 모두 지워서 보통은 401 INVALID_REFRESH_TOKEN이 와요(403은 정지와 동시에 온 요청에서만)")
  TokenResponse refresh(
      @Parameter(hidden = true) HttpServletRequest request,
      @Parameter(hidden = true) HttpServletResponse response);

  @Operation(
      summary = "로그아웃",
      description =
          "이 기기의 refresh token을 지우고 쿠키도 지워요. 다른 기기 로그인은 그대로예요. "
              + "쿠키가 없어도 204예요. 프론트는 메모리의 access token을 버려요.")
  @ApiResponse(responseCode = "204", description = "로그아웃했어요")
  ResponseEntity<Void> logout(
      @Parameter(hidden = true) HttpServletRequest request,
      @Parameter(hidden = true) HttpServletResponse response);
}
