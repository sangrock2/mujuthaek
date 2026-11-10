package kr.mujuthaek.api.notice.service;

import java.time.LocalDate;
import java.util.List;
import java.util.UUID;
import tools.jackson.databind.JsonNode;

/**
 * 판정용 창업지원 사업 하나 (판정 담당 요청 「판정을 위한 데이터 가공 요청안」 창업지원).
 *
 * @param programId 지원사업 ID (수집 DB 정책 ID, raw.policy.collected의 rawPolicyId)
 * @param version 사업 공고 버전 (수집 버전, 바뀌면 올라가는 값)
 * @param applyStart 신청 시작일 (모르면 null)
 * @param applyEnd 신청 마감일. null이면 상시 모집 (마감일을 모르는데 상시도 아닌 사업은 목록에 넣지 않아요)
 * @param regionCodes 지원 지역 법정동 10자리 (시군구 5자리 뒤를 0으로 채움). 전국 사업은 빈 목록
 * @param frame 판정 틀 그대로 (startup-support-judgment.v1)
 * @param detailUrl 수집한 사업 원문 주소 (모르면 null). 판정 목록의 사업공간 모집 정책과 같은 뜻
 */
public record ProgramForJudgment(
    UUID programId,
    int version,
    String title,
    LocalDate applyStart,
    LocalDate applyEnd,
    List<String> regionCodes,
    JsonNode frame,
    String detailUrl) {}
