package kr.mujuthaek.notification.notification;

import java.util.List;
import java.util.UUID;

/**
 * notification.requested의 payload (contracts/schemas/notification-events.draft.md).
 *
 * <p>받을 사람(recipients)·받을 주소·문구(title·body)·조용한 시간은 api가 회원 설정까지 보고 정해서 보내요. 알림 서버는 이 값을 다시 따지지 않고
 * 그대로 보내요.
 */
public record NotificationRequest(
    NotificationType type,
    String dedupKey,
    Target target,
    String title,
    String body,
    String linkPath,
    List<Recipient> recipients) {

  static final int MAX_RECIPIENTS = 500;

  public record Target(TargetType type, UUID id) {}

  /**
   * 받을 회원 1명.
   *
   * @param email 이메일로 보낼 주소. api가 "이메일 켬 + 이 종류 켬 + 인증된 주소"일 때만 넣고, 아니면 null
   * @param quietEnabled 22:00~08:00 알림을 08:00에 보내기
   * @param push 웹 푸시로 보낼 구독 기기 (contracts/schemas/web-push.draft.md 3장). api가 "이 종류 켬 + 기기 1대 이상"일
   *     때만 넣고, 아니면 null. 최대 5대
   * @param inboxId 이 회원의 api 알림함 줄 ID. 웹 푸시에 실어 보내면 기기가 「떴어요·눌렀어요」를 이 ID로 api에 알려요. 예전 요청은 null
   */
  public record Recipient(
      UUID userId, String email, boolean quietEnabled, List<PushDevice> push, UUID inboxId) {

    public Recipient(UUID userId, String email, boolean quietEnabled, List<PushDevice> push) {
      this(userId, email, quietEnabled, push, null);
    }

    /** 이메일만 받는 회원 (푸시 기기 없음) */
    public static Recipient emailOnly(UUID userId, String email, boolean quietEnabled) {
      return new Recipient(userId, email, quietEnabled, null);
    }

    @Override
    public String toString() {
      return "Recipient[userId=" + userId + ", quietEnabled=" + quietEnabled + "]";
    }
  }

  /**
   * 구독 기기 1대. 알면 그 기기에 알림을 보낼 수 있는 값이라 로그에 남기지 않아요 (toString도 가려요).
   *
   * @param endpoint 푸시 서비스 주소
   * @param p256dh 내용 암호화 공개키 (base64url)
   * @param auth 내용 암호화 비밀값 (base64url)
   */
  public record PushDevice(String endpoint, String p256dh, String auth) {
    @Override
    public String toString() {
      return "PushDevice[***]";
    }
  }

  /** 계약에 맞지 않으면 IllegalArgumentException. 다시 받아도 같아서 실패 큐로 보내요. */
  public void validate() {
    require(type != null, "type이 없어요");
    require(notBlank(dedupKey), "dedupKey가 없어요");
    require(target != null && target.type() != null && target.id() != null, "target이 없어요");
    require(notBlank(title) && notBlank(body), "title·body가 없어요");
    require(linkPath != null && linkPath.startsWith("/"), "linkPath가 이상해요");
    require(recipients != null && !recipients.isEmpty(), "recipients가 비었어요");
    require(recipients.size() <= MAX_RECIPIENTS, "recipients는 " + MAX_RECIPIENTS + "명까지예요");
    require(
        recipients.stream().allMatch(r -> r != null && r.userId() != null), "userId가 없는 회원이 있어요");
  }

  private static boolean notBlank(String value) {
    return value != null && !value.isBlank();
  }

  private static void require(boolean ok, String message) {
    if (!ok) {
      throw new IllegalArgumentException(message);
    }
  }
}
