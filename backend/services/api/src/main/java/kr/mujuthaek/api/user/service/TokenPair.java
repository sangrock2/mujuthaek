package kr.mujuthaek.api.user.service;

import java.time.Duration;

/**
 * 로그인·재발급 결과.
 *
 * @param accessToken JWT. 프론트는 메모리에 두고 Authorization: Bearer 로 보내요
 * @param accessTokenTtl access token 유효 시간
 * @param refreshToken 원문. HttpOnly 쿠키로만 내려보내요
 * @param refreshTokenTtl 쿠키 Max-Age
 */
public record TokenPair(
    String accessToken, Duration accessTokenTtl, String refreshToken, Duration refreshTokenTtl) {}
