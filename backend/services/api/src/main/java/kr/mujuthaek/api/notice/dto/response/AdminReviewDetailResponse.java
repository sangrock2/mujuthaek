package kr.mujuthaek.api.notice.dto.response;

import java.time.OffsetDateTime;
import java.util.List;
import tools.jackson.databind.JsonNode;

/**
 * 관리자 검수 상세: 머리, 확인할 칸(이유 포함), 원문 근거, 처리 기록.
 *
 * @param reason MUST · CHECK · FORMAT ({@link AdminReviewListResponse.Item#reason()}와 같아요)
 * @param reviewStatus PENDING · APPROVED · REJECTED · SUPERSEDED
 * @param field 공고 분야 (HOUSING 등)
 * @param provider 공급 기관 (예: LH)
 * @param detailUrl 기관 공고 원문 페이지 주소 (수집기가 준 값, 없으면 null)
 * @param issues 이슈 코드와 가리키는 칸 (예: VALUE_NOT_IN_QUOTE, /eligibility/3/value)
 * @param fields 사람이 확인할 칸. 신뢰도 숫자 대신 상태와 이유를 줘요
 * @param sources 확인할 칸의 원문 근거(쪽·인용문). 화면의 원문 강조에 써요
 * @param edits 고쳐서 승인한 칸 [{path, before, after}] (처리 전이면 빈 목록)
 * @param impact 승인하면 무엇이 바뀌는지 안내 (사람 수 대신, 사용자 소득을 저장하지 않아 판정이 바뀌는 사람은 셀 수 없어요). 처리가 끝났으면 null
 */
public record AdminReviewDetailResponse(
    String id,
    String reason,
    String reviewStatus,
    String title,
    String field,
    String provider,
    String sourceCode,
    Integer rawVersion,
    String rawPostId,
    String detailUrl,
    OffsetDateTime receivedAt,
    List<Issue> issues,
    List<Field> fields,
    List<Source> sources,
    String note,
    String decidedBy,
    List<Edit> edits,
    String impact,
    List<LogEntry> log) {

  /** target은 이슈가 가리키는 칸(JSON Pointer). 공고 전체에 대한 이슈면 null. */
  public record Issue(String code, String target) {}

  /**
   * 확인할 칸 하나.
   *
   * @param path 칸 위치(JSON Pointer). 칸별 수정에 그대로 써요
   * @param section 섹션 이름 (자격 조건·일정 등)
   * @param label 화면에 보일 칸 이름
   * @param status HELD 확인 전까지 화면·판정에 쓰지 않는 칸 · CHECK 보이지만 확인이 필요한 칸
   * @param value 칸 값. 글자·숫자면 그 값, 목록·묶음이면 null(설명은 display)
   * @param display 값을 한 줄로 (묶음이면 설명·원문)
   * @param editable 칸별 수정으로 바꿀 수 있는 값인지(글자·숫자·참거짓·null)
   * @param reasons 확인해야 하는 이유 (사람이 읽는 문장)
   * @param codes 이유 코드
   * @param sourceIds 이 칸의 원문 근거 ID ({@link Source#id()})
   */
  public record Field(
      String path,
      String section,
      String label,
      String status,
      JsonNode value,
      String display,
      boolean editable,
      List<String> reasons,
      List<String> codes,
      List<String> sourceIds) {}

  /** 원문 근거. page는 없을 수 있어요. */
  public record Source(String id, Integer page, String quote) {}

  /** 고친 칸. */
  public record Edit(String path, JsonNode before, JsonNode after) {}

  /** 처리 기록 한 줄. who: 시스템 · 검수자(로그인 계정 ID). */
  public record LogEntry(OffsetDateTime at, String who, String text) {}
}
