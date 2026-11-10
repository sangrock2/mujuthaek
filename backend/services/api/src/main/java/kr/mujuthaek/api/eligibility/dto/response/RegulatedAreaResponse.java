package kr.mujuthaek.api.eligibility.dto.response;

import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.util.UUID;

/**
 * 규제지역 한 줄.
 *
 * @param active 오늘 지정 중인지
 */
public record RegulatedAreaResponse(
    UUID id,
    String regionCode,
    String kind,
    String scopeNote,
    LocalDate validFrom,
    LocalDate validUntil,
    boolean active,
    String source,
    String updatedBy,
    OffsetDateTime updatedAt) {}
