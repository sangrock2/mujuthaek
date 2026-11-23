package kr.mujuthaek.api.user.controller.spec;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.tags.Tag;
import kr.mujuthaek.api.user.controller.EmailNotificationController.Address;
import kr.mujuthaek.api.user.controller.EmailNotificationController.Token;
import kr.mujuthaek.api.user.service.EmailNotificationService.Settings;
import kr.mujuthaek.api.user.service.EmailNotificationService.Status;
import kr.mujuthaek.api.user.service.LoginUser;

@Tag(name = "이메일 알림 설정", description = "직접 등록한 주소를 인증하고 별도 수신 동의 후 알림을 받습니다.")
public interface EmailNotificationApiSpec {
  @Operation(summary = "내 이메일 알림 상태")
  Status get(@Parameter(hidden = true) LoginUser user);

  @Operation(summary = "이메일 인증 메일 요청", description = "수집·이용 동의가 필요하며 1분 간격·하루 5회까지 요청합니다.")
  Status request(@Parameter(hidden = true) LoginUser user, Address body);

  @Operation(summary = "이메일 주소 인증", description = "요청한 계정에서 15분·1회용 링크를 확인합니다. 수신 동의는 별도입니다.")
  Status verify(@Parameter(hidden = true) LoginUser user, Token body);

  @Operation(summary = "이메일 알림 수신 설정 저장")
  Status save(@Parameter(hidden = true) LoginUser user, Settings body);

  @Operation(summary = "알림 이메일 수정 시작", description = "기존 주소의 인증 링크와 알림 수신 동의를 해제합니다.")
  Status edit(@Parameter(hidden = true) LoginUser user);

  @Operation(summary = "알림 이메일 수신 동의 철회")
  void remove(@Parameter(hidden = true) LoginUser user);
}
