package kr.mujuthaek.api.notification.dto.response;

import java.time.Instant;
import java.util.UUID;

/**
 * 내 푸시 기기 한 대. 주소·키는 주지 않아요.
 *
 * @param userAgent 등록할 때 보낸 이름. 없을 수 있어요
 * @param updatedAt 마지막 등록 (PWA가 앱을 열 때마다 다시 등록해서 최근에 쓴 때예요)
 */
public record PushDeviceResponse(UUID id, String userAgent, Instant createdAt, Instant updatedAt) {}
