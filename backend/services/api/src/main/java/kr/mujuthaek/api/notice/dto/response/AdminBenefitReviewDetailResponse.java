package kr.mujuthaek.api.notice.dto.response;

import java.time.OffsetDateTime;
import java.util.List;
import tools.jackson.databind.JsonNode;

/**
 * 혜택(주거·이주 정책) 검수 상세. 정제 결과와 받은 원문을 나란히 보여 주고, 칸별로 고쳐 승인해요.
 *
 * @param reasons 확인할 이유 (목록과 같음)
 * @param note 처리 메모 또는 제보로 다시 연 까닭
 * @param result 정제 결과 (policy.extracted payload: 요약·지원 내용·일정·자격 조건과 근거·품질). 칸별 수정의 path는 이 객체 기준
 *     JSON Pointer(예: /conditions/0/value, /supports/1/amountMax)이고, 원본·버전·출처(source)·품질(quality)
 *     칸은 못 고쳐요
 * @param edits 처리한 칸별 수정 [{path, before, after}] (대기 중이면 null)
 * @param source 받은 원본
 */
public record AdminBenefitReviewDetailResponse(
    String id,
    String rawPolicyId,
    int rawVersion,
    String status,
    List<String> reasons,
    String note,
    OffsetDateTime queuedAt,
    OffsetDateTime decidedAt,
    String decidedBy,
    JsonNode result,
    JsonNode edits,
    Source source) {

  /**
   * 받은 원본 (수집기 raw.policy.collected).
   *
   * @param text 원문 글 (API 항목·원문 화면을 이어 붙인 것)
   * @param documentStatus 첨부 공고문 상태 (NONE·BLOCKED 등)
   */
  public record Source(
      String title,
      String agency,
      String detailUrl,
      String applyUrl,
      List<String> categories,
      String text,
      String documentStatus) {}
}
