package kr.mujuthaek.notification.delivery.push;

import java.time.Duration;

/**
 * 푸시 서비스의 답.
 *
 * @param status HTTP 상태 코드
 * @param retryAfter 429·503 등에서 기다리라고 한 시간 (Retry-After). 없으면 null
 */
public record PushResponse(int status, Duration retryAfter) {}
