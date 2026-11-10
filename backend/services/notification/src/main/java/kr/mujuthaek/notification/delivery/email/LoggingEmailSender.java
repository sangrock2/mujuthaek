package kr.mujuthaek.notification.delivery.email;

import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

/** 보내지 않고 로그만 남겨요 (notification.mail.provider=log, 기본). 받는 주소와 본문은 남기지 않아요. */
@Component
@ConditionalOnProperty(
    name = "notification.mail.provider",
    havingValue = "log",
    matchIfMissing = true)
class LoggingEmailSender implements EmailSender {

  private static final Logger log = LoggerFactory.getLogger(LoggingEmailSender.class);

  @Override
  public String send(EmailMessage message) {
    String id = "log-" + UUID.randomUUID();
    log.info("메일 (보내지 않음): messageId={}, subject={}", id, message.subject());
    return id;
  }
}
