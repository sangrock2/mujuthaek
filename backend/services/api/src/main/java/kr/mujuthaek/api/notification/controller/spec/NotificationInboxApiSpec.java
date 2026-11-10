package kr.mujuthaek.api.notification.controller.spec;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.util.UUID;
import kr.mujuthaek.api.common.dto.response.CursorPageResponse;
import kr.mujuthaek.api.notification.dto.response.NotificationItemResponse;
import kr.mujuthaek.api.notification.dto.response.UnreadCountResponse;
import kr.mujuthaek.api.user.service.LoginUser;
import org.springframework.http.ResponseEntity;

@Tag(name = "알림함", description = "내 알림 목록과 읽음 처리예요. 로그인한 회원만 부를 수 있고, 알림은 90일 동안 남아요.")
public interface NotificationInboxApiSpec {

  @Operation(
      summary = "내 알림 목록",
      description = "최근 것부터 줘요. 응답의 nextCursor를 다음 요청의 cursor로 넘기면 이어서 받아요(hasNext가 false면 끝).")
  @ApiResponse(responseCode = "200", description = "알림 목록")
  @ApiResponse(
      responseCode = "400",
      description = "VALIDATION_FAILED — size가 1~100 밖이에요. INVALID_CURSOR — cursor가 올바르지 않아요")
  CursorPageResponse<NotificationItemResponse> list(
      @Parameter(hidden = true) LoginUser user,
      @Parameter(description = "이전 응답의 nextCursor. 첫 요청이면 비워요") String cursor,
      @Parameter(description = "한 번에 받을 개수 (기본 20, 1~100)", example = "20") Integer size,
      @Parameter(description = "true면 안 읽은 알림만") boolean unread);

  @Operation(summary = "안 읽은 알림 수")
  UnreadCountResponse unreadCount(@Parameter(hidden = true) LoginUser user);

  @Operation(summary = "알림 하나 읽음", description = "이미 읽었어도 204예요.")
  @ApiResponse(responseCode = "204", description = "읽음으로 바꿨어요")
  @ApiResponse(responseCode = "404", description = "NOTIFICATION_NOT_FOUND — 내 알림이 아니거나 없어요")
  ResponseEntity<Void> markRead(
      @Parameter(hidden = true) LoginUser user, @Parameter(description = "알림 ID") UUID id);

  @Operation(summary = "내 알림 모두 읽음", description = "안 읽은 알림이 없어도 204예요.")
  @ApiResponse(responseCode = "204", description = "모두 읽음으로 바꿨어요")
  ResponseEntity<Void> markAllRead(@Parameter(hidden = true) LoginUser user);
}
