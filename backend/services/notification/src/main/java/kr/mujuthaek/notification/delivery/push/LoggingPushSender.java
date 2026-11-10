package kr.mujuthaek.notification.delivery.push;

import java.net.URI;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

/** 보내지 않고 로그만 남겨요 (notification.push.provider=log, 기본). 기기 주소·키·내용은 남기지 않아요. */
@Component
@ConditionalOnProperty(
    name = "notification.push.provider",
    havingValue = "log",
    matchIfMissing = true)
class LoggingPushSender implements PushSender {

  private static final Logger log = LoggerFactory.getLogger(LoggingPushSender.class);

  @Override
  public PushResponse send(PushMessage message) {
    log.info(
        "푸시 (보내지 않음): host={}, bytes={}, ttl={}",
        URI.create(message.device().endpoint()).getHost(),
        message.payload().length,
        message.ttl());
    return new PushResponse(201, null);
  }
}
