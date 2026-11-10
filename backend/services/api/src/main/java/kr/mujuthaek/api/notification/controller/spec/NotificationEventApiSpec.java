package kr.mujuthaek.api.notification.controller.spec;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.util.UUID;
import org.springframework.http.ResponseEntity;

@Tag(
    name = "알림 반응 기록",
    description =
        "알림을 봤는지·눌렀는지 알려 받아요. 웹 푸시를 받은 서비스 워커는 로그인 토큰이 없어서 로그인 없이 알림 ID만으로 받아요. "
            + "처음 한 번만 적고, 그 알림이 있는지는 알려 주지 않아요(늘 204).")
public interface NotificationEventApiSpec {

  @Operation(summary = "웹 푸시가 기기에 떴어요")
  @ApiResponse(responseCode = "204", description = "받았어요 (알림이 없어도 204)")
  ResponseEntity<Void> shown(@Parameter(description = "알림 ID") UUID id);

  @Operation(
      summary = "알림을 눌러 그 화면으로 갔어요",
      description = "푸시나 알림 목록에서 눌렀을 때 불러요. 아직 안 읽은 알림이면 읽음도 함께 남겨요.")
  @ApiResponse(responseCode = "204", description = "받았어요 (알림이 없어도 204)")
  ResponseEntity<Void> clicked(@Parameter(description = "알림 ID") UUID id);
}
