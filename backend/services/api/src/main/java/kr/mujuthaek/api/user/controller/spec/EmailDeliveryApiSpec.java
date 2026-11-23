package kr.mujuthaek.api.user.controller.spec;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.tags.Tag;
import kr.mujuthaek.api.user.controller.EmailDeliveryController.Check;
import kr.mujuthaek.api.user.controller.EmailDeliveryController.Token;
import kr.mujuthaek.api.user.service.EmailNotificationService.Eligibility;

@Tag(name = "이메일 수신 해제·발송 확인", description = "메일의 서명된 수신 해제 링크와 내부 발송 직전 동의 확인")
public interface EmailDeliveryApiSpec {
  @Operation(summary = "로그인 없이 알림 이메일 주소 인증", description = "메일에 담은 단회용 인증 토큰을 확인합니다.")
  @ApiResponse(responseCode = "204", description = "알림 이메일 주소를 인증했습니다")
  void verify(Token body);

  @Operation(summary = "발송 직전 이메일 수신 동의 확인", description = "알림 서버 전용 비밀 헤더를 확인합니다.")
  Eligibility eligible(@Parameter(hidden = true) String token, Check body);

  @Operation(summary = "메일 링크로 이메일 알림 수신 해제", description = "로그인 없이 유효한 서명으로 주소와 수신 동의를 철회합니다.")
  void unsubscribe(Token body);

  @Operation(
      summary = "메일 앱의 수신 거부 버튼으로 이메일 알림 수신 해제",
      description =
          "알림 메일의 List-Unsubscribe·List-Unsubscribe-Post 머리글(RFC 8058)이 가리키는 주소예요. 메일 앱이 로그인 없이 "
              + "본문 List-Unsubscribe=One-Click 폼을 POST해요. 본문은 보지 않고 주소의 서명된 토큰만 봐요. 메일 본문에 있는 링크와 같은 방식으로 주소와 수신 동의를 철회해요.")
  @ApiResponse(responseCode = "200", description = "수신 동의를 철회했어요")
  @ApiResponse(
      responseCode = "400",
      description = "EMAIL_VERIFICATION_INVALID — 토큰 형식·서명이 맞지 않아요. VALIDATION_FAILED — token이 없어요")
  void unsubscribeOneClick(@Parameter(description = "메일 머리글에 실린 서명된 수신 해제 토큰") String token);
}
