package kr.mujuthaek.api.notice.dto.response;

import java.time.OffsetDateTime;
import java.util.List;

/**
 * 정정 이력 한 줄.
 *
 * @param kind NOTICE 모집공고 · CORRECTION 정정
 * @param changedFields 앞 버전과 비교해 바뀐 목록 값 (첫 버전은 빈 목록)
 */
public record NoticeVersionResponse(
    int version,
    String kind,
    String reviewStatus,
    List<String> changedFields,
    OffsetDateTime receivedAt) {}
