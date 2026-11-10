package kr.mujuthaek.notification.delivery.email;

import kr.mujuthaek.notification.delivery.DeliveryException;

/** 메일을 실제로 내보내는 부품. 운영은 {@link SesEmailSender}, 로컬 기본은 {@link LoggingEmailSender}, 테스트는 가짜를 써요. */
public interface EmailSender {

  /**
   * @return 발송 서비스가 준 MessageId
   */
  String send(EmailMessage message) throws DeliveryException;
}
