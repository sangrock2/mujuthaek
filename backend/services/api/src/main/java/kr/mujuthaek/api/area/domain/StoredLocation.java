package kr.mujuthaek.api.area.domain;

import java.util.UUID;
import kr.mujuthaek.api.area.domain.GeocodeResult.FailReason;
import kr.mujuthaek.api.area.domain.GeocodeResult.Status;

/**
 * area.notice_locations에 저장된 공고 위치 한 줄.
 *
 * @param locationId area 위치 ID (API의 siteId)
 * @param coordinate 좌표가 없으면(FAILED) null
 * @param failReason FAILED일 때만
 */
public record StoredLocation(
    UUID locationId,
    UUID noticeId,
    String noticeLocationId,
    int noticeVersion,
    String addressText,
    String bjdCodeGiven,
    Status status,
    FailReason failReason,
    Coordinate coordinate) {}
