package kr.mujuthaek.api.benefit.service;

import java.time.LocalDate;
import java.util.List;
import java.util.UUID;

/**
 * 다른 모듈(알림)이 혜택 ID로 조회하는 혜택 요약 (BenefitQueryService.findSummary). 알림 문구·대상자 확인·마감 알림에 써요.
 *
 * @param field BENEFIT
 * @param version 반영한 수집 버전
 * @param status UPCOMING · OPEN · CLOSED · HIDDEN (숨김도 줘요, 거르는 건 부르는 쪽)
 * @param applyEnd 신청 마감일 (상시거나 모르면 null)
 * @param regionScope NATIONWIDE · SIDO · SIGUNGU · UNKNOWN
 * @param regionCodes 시도 2자리 / 시군구 5자리
 */
public record BenefitSummary(
    UUID benefitId,
    String field,
    int version,
    String title,
    String agency,
    String status,
    LocalDate applyStart,
    LocalDate applyEnd,
    boolean applyAlways,
    String regionScope,
    List<String> regionCodes,
    String detailUrl) {}
