package kr.mujuthaek.api.notice.service;

import java.time.LocalDate;
import java.util.List;
import java.util.UUID;

/**
 * 다른 모듈(알림 등)이 공고 ID로 조회하는 공고 요약 (NoticeQueryService.findSummaries). 목록·상세 API 응답과 달리 오늘 기준 값(D-day
 * 등)은 넣지 않아요.
 *
 * @param noticeId 공고 ID. 다른 공고에 합쳐진 공고 ID로 물으면 합친(남은) 공고의 ID라 물은 ID와 다를 수 있어요
 * @param version 공고 버전 (정정되면 올라가는 값)
 * @param field 공고 분야 HOUSING · BUSINESS_SPACE
 * @param provider 공급 기관 (모르면 null)
 * @param noticeType 공고 유형 (모르면 null)
 * @param status 접수 상태 UPCOMING · APPLYING · ALWAYS · CLOSED · UNKNOWN (마감된 공고도 줘요)
 * @param applyStart 접수 시작일 (모르면 null)
 * @param applyEnd 접수 마감일 (상시거나 모르면 null)
 * @param regionCodes 공고가 걸친 지역의 법정동 10자리 (시군구 5자리 뒤를 0으로 채움). NoticeForJudgment와 같은 뜻: 전국 공고는 빈 목록,
 *     지역을 모르면(위치 지역 보류·코드 없음) null
 * @param nationwide 전국 대상 공고면 true
 * @param detailPath 공고 상세 API 경로 (/api/v1/notices/{noticeId})
 * @param detailUrl 기관 원문 주소 (모르면 null)
 */
public record NoticeSummary(
    UUID noticeId,
    int version,
    String field,
    String title,
    String provider,
    String noticeType,
    String status,
    LocalDate applyStart,
    LocalDate applyEnd,
    List<String> regionCodes,
    boolean nationwide,
    String detailPath,
    String detailUrl) {}
