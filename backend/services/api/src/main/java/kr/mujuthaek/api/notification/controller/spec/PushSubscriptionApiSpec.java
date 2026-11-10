package kr.mujuthaek.api.notification.controller.spec;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.util.List;
import java.util.UUID;
import kr.mujuthaek.api.notification.dto.request.PushSubscribeRequest;
import kr.mujuthaek.api.notification.dto.request.PushUnsubscribeRequest;
import kr.mujuthaek.api.notification.dto.response.PushDeviceResponse;
import kr.mujuthaek.api.notification.dto.response.PushPublicKeyResponse;
import kr.mujuthaek.api.user.service.LoginUser;
import org.springframework.http.ResponseEntity;

@Tag(
    name = "웹 푸시 구독",
    description = "웹 푸시 공개키와 내 기기 등록·해제예요. 공개키는 로그인 없이, 기기 등록·해제·목록은 로그인한 회원만 부를 수 있어요.")
public interface PushSubscriptionApiSpec {

  @Operation(
      summary = "VAPID 공개키",
      description = "PWA가 pushManager.subscribe({applicationServerKey})에 넣는 base64url 공개키예요.")
  @ApiResponse(responseCode = "200", description = "공개키")
  @ApiResponse(responseCode = "503", description = "PUSH_NOT_CONFIGURED — 서버에 공개키 설정이 없어요")
  PushPublicKeyResponse publicKey();

  @Operation(
      summary = "이 기기 등록·갱신",
      description =
          "브라우저 subscription.toJSON() 모양에 userAgent(기기 목록에 보여 줄 이름, 200자를 넘으면 잘라요)를 더해 보내요. "
              + "PWA는 앱을 열 때마다 현재 구독을 보내요. "
              + "endpoint는 허용된 푸시 서비스 도메인의 https 주소(2048자까지), keys.p256dh(풀면 65바이트)·keys.auth(풀면 16바이트)는 base64url이에요. "
              + "다른 회원이 쓰던 주소면 이 회원으로 옮기고, 기기가 회원당 최대 수(기본 5대)를 넘으면 가장 오래 안 쓴 기기를 지워요.")
  @ApiResponse(responseCode = "204", description = "등록했어요")
  @ApiResponse(
      responseCode = "400",
      description =
          "VALIDATION_FAILED — keys가 없거나, endpoint·keys.p256dh·keys.auth가 비었거나 형식이 맞지 않아요")
  @ApiResponse(responseCode = "503", description = "PUSH_NOT_CONFIGURED — 서버에 공개키 설정이 없어요")
  ResponseEntity<Void> subscribe(
      @Parameter(hidden = true) LoginUser user, PushSubscribeRequest request);

  @Operation(
      summary = "이 기기 또는 내 기기 모두 해제",
      description =
          "scope 없이 본문의 endpoint로 이 기기를 해제해요(subscription.toJSON()을 그대로 보내도 돼요). "
              + "scope=all이면 본문은 보지 않고 내 기기를 모두 해제해요. 해제할 기기가 없거나 다른 회원 기기여도 204예요.")
  @ApiResponse(responseCode = "204", description = "해제했어요")
  @ApiResponse(
      responseCode = "400",
      description = "VALIDATION_FAILED — scope가 all이 아니거나, scope 없이 본문의 endpoint가 비었어요")
  ResponseEntity<Void> unsubscribe(
      @Parameter(hidden = true) LoginUser user,
      @Parameter(description = "all이면 내 기기 모두 해제. all만 돼요", example = "all") String scope,
      PushUnsubscribeRequest request);

  @Operation(summary = "내 기기 목록", description = "최근에 쓴 기기부터 줘요. 주소·키는 주지 않아요.")
  List<PushDeviceResponse> devices(@Parameter(hidden = true) LoginUser user);

  @Operation(summary = "목록에서 고른 기기 해제")
  @ApiResponse(responseCode = "204", description = "해제했어요")
  @ApiResponse(responseCode = "404", description = "PUSH_SUBSCRIPTION_NOT_FOUND — 내 기기가 아니거나 없어요")
  ResponseEntity<Void> remove(
      @Parameter(hidden = true) LoginUser user, @Parameter(description = "기기 ID (목록의 id)") UUID id);
}
