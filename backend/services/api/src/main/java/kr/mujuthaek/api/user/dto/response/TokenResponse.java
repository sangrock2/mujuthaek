package kr.mujuthaek.api.user.dto.response;

/**
 * access token 응답. refresh token은 본문에 넣지 않고 HttpOnly 쿠키로만 보내요.
 *
 * @param expiresIn access token 남은 시간 (초)
 */
public record TokenResponse(String accessToken, String tokenType, long expiresIn) {}
