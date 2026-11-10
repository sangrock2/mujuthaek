package kr.mujuthaek.api.common.event;

import java.util.List;
import java.util.UUID;

/**
 * 새 혜택이 보이게 됨. 처음 저장한 범위 안 정책이거나, 범위 밖(숨김)이던 정책이 새 버전에서 범위 안이 된 때 보내요. notification(사용자 알림)이 받아 관심
 * 지역이 맞는 회원에게 알려요. 과거 정책 재처리(reprocess)는 보내지 않아요. 제목 말고 알림에 쓸 값은 BenefitQueryService.findSummary로
 * 조회하세요.
 *
 * @param field BENEFIT (지금은 주거 혜택만 저장해요)
 * @param regionScope NATIONWIDE · SIDO · SIGUNGU · UNKNOWN (benefits.region_scope)
 * @param regionCodes 시도 2자리 / 시군구 5자리 (benefits.region_codes, 전국이면 빈 목록)
 */
public record BenefitPublished(
    UUID benefitId,
    String field,
    String regionScope,
    List<String> regionCodes,
    String title,
    boolean reprocess) {}
