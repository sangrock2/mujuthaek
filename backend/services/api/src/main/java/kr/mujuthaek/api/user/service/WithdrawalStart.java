package kr.mujuthaek.api.user.service;

import java.time.Duration;
import java.util.List;

/**
 * 탈퇴 시작 결과.
 *
 * @param provider 다시 로그인할 소셜 (KAKAO, NAVER, GOOGLE)
 * @param ticket 일회용 티켓 원문. 재인증 주소의 withdraw 파라미터로만 써요
 * @param ttl 티켓 유효 시간
 * @param otherProviders 함께 연결된 다른 소셜. 탈퇴하면 우리 쪽 연결은 지워지지만 그 서비스의 앱 동의는 남아서, 사용자가 직접 해제해야 해요
 */
public record WithdrawalStart(
    String provider, String ticket, Duration ttl, List<String> otherProviders) {}
