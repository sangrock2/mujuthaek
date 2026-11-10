package kr.mujuthaek.api.user.dto.response;

import java.util.List;

/**
 * 탈퇴 시작 응답. 프론트는 {@code reauthUrl}로 페이지를 이동시켜요 (fetch가 아니라 주소 이동).
 *
 * @param provider 다시 로그인할 소셜 (KAKAO, NAVER, GOOGLE)
 * @param reauthUrl 재인증 주소 ({@code /oauth2/authorization/{제공자}?withdraw=일회용 티켓})
 * @param expiresIn 티켓 유효 시간 (초)
 * @param otherProviders 함께 연결된 다른 소셜. 이 소셜들의 연결은 서버가 끊을 수 없어서, 탈퇴 전에 "각 서비스에서 직접 해제하세요"라고 보여 줘요
 */
public record WithdrawalResponse(
    String provider, String reauthUrl, long expiresIn, List<String> otherProviders) {}
