package kr.mujuthaek.api.common.event;

import java.util.List;
import java.util.UUID;

/**
 * 보이고 있던 혜택의 새 버전에서 사용자가 볼 내용이 바뀜. 바뀐 값 자체는 싣지 않으니 BenefitQueryService로 조회하세요. notification이 받아 관심
 * 혜택으로 둔 회원에게 정정 알림을 보내요.
 *
 * <p>changedFields는 바뀐 부분의 이름이에요 (이 순서로): basic(제목·기관) · region(지역) · schedule(신청·사업 기간) ·
 * supports(지원 내용) · conditions(자격 조건) · application(서류·문의처·신청 주소). AI가 다시 쓴 요약 글·근거 문장만 바뀐 것은 넣지
 * 않아요 (다시 추출할 때마다 정정 알림이 가지 않게).
 *
 * @param version 반영한 수집 버전 (benefits.source_version). 정정 알림 중복 방지 열쇠에 써요
 * @param reprocess 과거 자료 재처리 중 바뀐 것이면 true (사용자 알림을 보내지 않아요)
 */
public record BenefitUpdated(
    UUID benefitId, String field, int version, List<String> changedFields, boolean reprocess) {}
