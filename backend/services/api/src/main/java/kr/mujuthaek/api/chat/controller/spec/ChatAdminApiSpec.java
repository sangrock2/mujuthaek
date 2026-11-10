package kr.mujuthaek.api.chat.controller.spec;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.util.UUID;
import kr.mujuthaek.api.chat.domain.ReviewStatus;
import kr.mujuthaek.api.chat.dto.request.ReviewRequest;
import kr.mujuthaek.api.chat.dto.response.ChatReportResponse;
import kr.mujuthaek.api.common.dto.response.CursorPageResponse;
import kr.mujuthaek.api.user.service.LoginUser;
import org.springframework.http.ResponseEntity;

@Tag(
    name = "채팅 신고 검토",
    description = "신고된 채팅 메시지를 보고 가림 유지·다시 보이기를 정해요. 권한 CHAT이 있는 관리자만 부를 수 있어요.")
public interface ChatAdminApiSpec {

  @Operation(
      summary = "채팅 신고 목록",
      description =
          "검토 상태별 신고를 최신순으로 줘요. 가려지거나 작성자가 지운 메시지도 검토할 수 있게 본문을 보여주고, 신고한 회원은 보여주지 않아요. "
              + "응답의 nextCursor를 다음 요청의 cursor로 넘기면 이어서 받아요(hasNext가 false면 끝).")
  @ApiResponse(responseCode = "200", description = "신고 목록")
  @ApiResponse(
      responseCode = "400",
      description = "VALIDATION_FAILED — size가 1~100 밖이에요. INVALID_CURSOR — cursor가 올바르지 않아요")
  CursorPageResponse<ChatReportResponse> reports(
      @Parameter(description = "검토 상태 (기본 PENDING: 검토 전, KEPT_HIDDEN: 가림 유지함, RESTORED: 다시 보이게 함)")
          ReviewStatus status,
      @Parameter(description = "이전 응답의 nextCursor. 첫 요청이면 비워요") String cursor,
      @Parameter(description = "한 번에 받을 개수 (기본 20, 1~100)", example = "20") Integer size);

  @Operation(
      summary = "검토 전 신고 글 수",
      description = "사이드바 숫자예요. 검토 전 신고가 걸린 글 수이고, 같은 글에 신고가 여러 건이면 한 글로 세요.")
  ChatReportResponse.Counts counts();

  @Operation(
      summary = "신고된 메시지 처리",
      description =
          "action이 KEEP_HIDDEN이면 관리자 가림(HIDDEN_ADMIN)으로 두고, 보이던 메시지였으면 SSE message.hidden이 가요. "
              + "RESTORE면 다시 보이게(VISIBLE) 하고 검토 전 신고 수를 0으로 되돌리며, 가려져 있었으면 SSE message.restored가 가요. "
              + "그 메시지의 검토 전 신고는 모두 처리 결과로 바뀌고 처리한 관리자와 시각이 남아요. "
              + "작성자가 지운 메시지는 신고만 닫고 DELETED 그대로 둬요.")
  @ApiResponse(responseCode = "204", description = "처리했어요")
  @ApiResponse(responseCode = "400", description = "VALIDATION_FAILED — action이 없어요")
  @ApiResponse(responseCode = "404", description = "CHAT_MESSAGE_NOT_FOUND — 없는 메시지예요")
  ResponseEntity<Void> review(
      @Parameter(description = "메시지 ID") UUID id,
      ReviewRequest request,
      @Parameter(hidden = true) LoginUser user);
}
