package kr.mujuthaek.api.notification.dto.request;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotNull;

/**
 * PUT /api/users/me/push-subscriptions 본문. 브라우저 {@code subscription.toJSON()} 모양 그대로예요. 주소·키는 로그에
 * 남기면 안 돼서 toString에서 가려요.
 *
 * @param endpoint 이 기기로 가는 푸시 서비스 주소
 * @param keys 내용 암호화 키
 * @param userAgent 기기 목록에 보여 줄 이름 (예: Chrome / Android). 200자를 넘으면 잘라요
 */
public record PushSubscribeRequest(
    @Schema(requiredMode = Schema.RequiredMode.REQUIRED) String endpoint,
    @NotNull Keys keys,
    String userAgent) {

  public record Keys(
      @Schema(requiredMode = Schema.RequiredMode.REQUIRED) String p256dh,
      @Schema(requiredMode = Schema.RequiredMode.REQUIRED) String auth) {
    @Override
    public String toString() {
      return "Keys[***]";
    }
  }

  @Override
  public String toString() {
    return "PushSubscribeRequest[endpoint=***, keys=***, userAgent=" + userAgent + "]";
  }
}
