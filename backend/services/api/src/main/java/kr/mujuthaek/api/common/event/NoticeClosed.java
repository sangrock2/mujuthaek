package kr.mujuthaek.api.common.event;

import java.time.LocalDate;
import java.util.UUID;

/**
 * 공고 접수가 마감됨 (마감이 아니던 공고가 마감으로 바뀐 때 한 번). 날짜가 지나 마감되거나(접수 상태 재계산) 정정으로 마감일이 앞당겨져 마감된 때 보내요. 처음부터
 * 마감인 공고와 과거 공고 재처리(reprocess)는 보내지 않아요. 제목·마감일 등 알림에 쓸 값은 NoticeQueryService.findSummaries로 조회하세요.
 *
 * @param field 공고 분야 HOUSING · BUSINESS_SPACE
 * @param closedOn 마감일 (접수 기간 중 가장 늦은 마감일, 모르면 마감을 확인한 날)
 */
public record NoticeClosed(UUID noticeId, String field, LocalDate closedOn) {}
