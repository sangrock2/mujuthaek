package kr.mujuthaek.api.notice.dto.request;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import java.util.List;
import tools.jackson.databind.JsonNode;

/**
 * 승인·반려 본문 (모두 비워도 돼요).
 *
 * @param reason 반려 사유: DUPLICATE 중복 공고 · SOURCE_MISMATCH 원문과 다름(다시 추출) · OUT_OF_SCOPE 서비스 대상 아님 ·
 *     CLOSED 마감된 공고. 승인에서는 무시해요
 * @param note 검수자 메모
 * @param edits 고쳐서 승인할 칸 (상세의 fields[].path와 새 값). 반려에서는 무시해요
 */
public record AdminReviewDecisionRequest(
    RejectReason reason,
    @Size(max = 500) String note,
    @Size(max = 200) List<@Valid FieldEdit> edits) {

  /** 칸 하나 고치기. value는 그 칸의 새 값(글자·숫자·참거짓·null). */
  public record FieldEdit(@NotBlank @Size(max = 300) String path, JsonNode value) {}

  /** 프론트 반려 사유 선택지와 같은 순서예요. */
  public enum RejectReason {
    DUPLICATE("중복 공고"),
    SOURCE_MISMATCH("원문과 다름 · 다시 추출"),
    OUT_OF_SCOPE("서비스 대상 아님"),
    CLOSED("마감된 공고");

    private final String label;

    RejectReason(String label) {
      this.label = label;
    }

    public String label() {
      return label;
    }
  }
}
