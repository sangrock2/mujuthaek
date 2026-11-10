package kr.mujuthaek.notification.delivery;

import java.util.List;
import java.util.Optional;
import java.util.UUID;
import kr.mujuthaek.notification.notification.NotificationRequest;

/**
 * 발송 채널 하나 (이메일, 웹 푸시 …). 채널마다 다른 일은 여기에만 있어요.
 *
 * <p>발송 줄 만들기·중복 거르기·보낼 시각·재시도·결과 기록은 채널과 상관없이 {@code NotificationService}와 {@link DeliveryWorker}가
 * 해요. 새 채널은 이 인터페이스를 구현한 빈을 하나 추가하면 그대로 붙어요.
 */
public interface NotificationChannel {

  Channel channel();

  /**
   * 요청에 담긴 이 채널의 받을 곳. 없으면 발송 줄을 만들지 않아요. 이메일은 주소, 웹 푸시는 그 회원의 구독 기기 목록(JSON)이에요.
   *
   * <p>받을지 말지는 api가 정해서 넣거나 빼요. 채널은 요청에서 꺼내기만 해요. 회원 1명·채널 1개에 발송 줄 1개라, 기기가 여러 대인 푸시는 {@link
   * #send}에서 기기마다 보내요.
   */
  Optional<String> address(NotificationRequest.Recipient recipient);

  /** 묶음 종류(NotificationType.digest)를 모아 보내는 간격. 이메일은 하루 두 번, 웹 푸시는 30분마다. 비어 있으면 묶지 않고 바로 보내요 */
  Optional<DigestCadence> digestCadence();

  /**
   * {@link #address}가 준 곳에 보내요. 묶음이면 여러 건, 아니면 1건이에요.
   *
   * <p>받을 곳이 여러 개(푸시 기기)인데 일부만 보냈으면 {@link DeliveryException#remainingAddress()}에 못 보낸 곳만 담아 던져요.
   * 다시 보낼 때는 그곳에만 보내요.
   *
   * @param userId 받는 회원 (웹 푸시는 죽은 구독을 api에 알릴 때 써요)
   * @return 발송 서비스가 준 ID (SES MessageId 등). 반송 알림과 맞출 때 써요. 없으면 null
   */
  String send(UUID userId, String address, List<OutgoingNotification> notifications)
      throws DeliveryException;

  /**
   * 다시 보낼 받을 곳에 「앞 차례에 이미 받은 곳이 있다」는 표시가 있는지. 발송 중 예상 못한 오류가 나도 그 표시를 잃지 않게 발송 작업기가 물어요(2026-11-10
   * 재검토: 표시가 사라져 재시도를 다 쓰면 받은 알림이 FAILED로 남았음). 받을 곳이 하나뿐인 채널은 늘 false.
   */
  default boolean deliveredBefore(String address) {
    return false;
  }
}
