package kr.mujuthaek.api.eligibility.dto.response;

/**
 * 기준값 화면의 「이 값을 쓰는 규칙 N개」: 마감이 지나지 않은(접수 예정·접수 중·상시) 공고·창업지원 사업 중 판정 틀이 이 기준을 쓰는 수.
 *
 * @param kind MEDIAN_INCOME · URBAN_WORKER_INCOME(도시근로자 월평균소득 포함) · RANK_CRITERIA(신청 순위가 있는 판정 틀)
 * @param housing 주거 공고
 * @param businessSpace 사업공간 공고·모집
 * @param startupSupport 창업지원 사업
 */
public record CriteriaUsageResponse(
    String kind, int housing, int businessSpace, int startupSupport, int total) {}
