package kr.mujuthaek.api.area.dto.request;

import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

/**
 * 생활권 제보 처리 끝.
 *
 * @param result FIXED 고침 · KEPT 그대로 둠
 * @param reply 제보한 회원에게 보낼 답 (비우면 답장 없음)
 * @param group 같은 공고·항목의 처리 전 제보도 같이 끝낼지 (기본 true)
 */
public record AreaReportResolveRequest(
    @NotNull Result result, @Size(max = 1000) String reply, Boolean group) {

  public enum Result {
    FIXED,
    KEPT
  }
}
