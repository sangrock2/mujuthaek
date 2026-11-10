package kr.mujuthaek.api.notification.dto.response;

/**
 * 웹 푸시 구독에 쓰는 VAPID 공개키.
 *
 * @param publicKey base64url. PWA가 {@code pushManager.subscribe({applicationServerKey})}에 넣어요
 */
public record PushPublicKeyResponse(String publicKey) {}
