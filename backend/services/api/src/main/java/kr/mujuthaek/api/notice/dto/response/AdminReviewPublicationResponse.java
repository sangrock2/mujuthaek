package kr.mujuthaek.api.notice.dto.response;

import java.util.UUID;

/** 검수 이벤트의 공개 반영 결과. 아직 수신 기록이 없으면 PENDING. */
public record AdminReviewPublicationResponse(String outcome, UUID publicId, Integer version) {
  public static AdminReviewPublicationResponse pending() {
    return new AdminReviewPublicationResponse("PENDING", null, null);
  }
}
