package kr.mujuthaek.notification.delivery;

import java.time.Duration;
import java.util.Optional;

/**
 * 채널이 보내지 못했을 때. {@code permanent}면 다시 보내도 안 되는 실패라 바로 FAILED, 아니면 뒤로 미뤄 다시 보내요.
 *
 * <p>{@code code}는 deliveries.last_error에 남아요. 이메일 주소·푸시 주소 같은 개인 정보는 넣지 않아요.
 */
public class DeliveryException extends Exception {

  private final String code;
  private final boolean permanent;
  private final String remainingAddress;
  private final Duration retryAfter;
  private final boolean delivered;

  public DeliveryException(String code, boolean permanent, Throwable cause) {
    super(code, cause);
    this.code = code;
    this.permanent = permanent;
    this.remainingAddress = null;
    this.retryAfter = null;
    this.delivered = false;
  }

  public DeliveryException(String code, boolean permanent) {
    this(code, permanent, null);
  }

  /**
   * 일부만 못 보낸 일시적인 실패 (웹 푸시 기기 여러 대).
   *
   * @param remainingAddress 다시 보낼 곳만 남긴 받을 곳. 이미 받은 곳은 빼서 두 번 받지 않아요
   * @param retryAfter 발송 서비스가 기다리라고 한 시간 (429 Retry-After). 없으면 null
   */
  public DeliveryException(String code, String remainingAddress, Duration retryAfter) {
    this(code, remainingAddress, retryAfter, false);
  }

  /**
   * @param delivered 받을 곳 하나라도 이미 받았는지 (웹 푸시 기기 한 대 이상). 그러면 남은 곳의 재시도를 다 써도 보낸 것(SENT)으로 적어요
   */
  public DeliveryException(
      String code, String remainingAddress, Duration retryAfter, boolean delivered) {
    super(code);
    this.code = code;
    this.permanent = false;
    this.remainingAddress = remainingAddress;
    this.retryAfter = retryAfter;
    this.delivered = delivered;
  }

  /** 받을 곳 하나라도 이미 받았는지 */
  public boolean delivered() {
    return delivered;
  }

  public String code() {
    return code;
  }

  public boolean permanent() {
    return permanent;
  }

  /** 다시 보낼 때 쓸 받을 곳. 비어 있으면 그대로 */
  public Optional<String> remainingAddress() {
    return Optional.ofNullable(remainingAddress);
  }

  public Optional<Duration> retryAfter() {
    return Optional.ofNullable(retryAfter);
  }
}
