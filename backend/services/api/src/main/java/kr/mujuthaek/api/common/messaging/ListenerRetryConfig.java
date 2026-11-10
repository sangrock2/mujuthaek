package kr.mujuthaek.api.common.messaging;

import kr.mujuthaek.api.common.alert.OpsAlert;
import org.springframework.amqp.AmqpRejectAndDontRequeueException;
import org.springframework.amqp.rabbit.retry.MessageRecoverer;
import org.springframework.amqp.rabbit.retry.RejectAndDontRequeueRecoverer;
import org.springframework.boot.amqp.autoconfigure.RabbitListenerRetrySettingsCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * 받기 재시도(application.yml spring.rabbitmq.listener.simple.retry)는 연결 오류처럼 잠깐 생긴 오류에만 해요. 계약에 맞지 않아
 * 던진 AmqpRejectAndDontRequeueException은 다시 해도 같아서 바로 실패 큐로 보내요. 재시도하면 2초·4초·8초 동안 같은 큐의 다음 메시지가
 * 기다려요.
 */
@Configuration
class ListenerRetryConfig {

  @Bean
  RabbitListenerRetrySettingsCustomizer doNotRetryPermanentFailures() {
    return settings -> settings.setExceptionPredicate(ListenerRetryConfig::retryable);
  }

  /**
   * 재시도를 다 하거나 다시 해도 같은 실패라 실패 큐(.dlq)로 보낼 때 슬랙으로 알려요. 보내는 일은 기본과 같아요(거절, 다시 넣지 않음 → 큐의 DLX로). 메시지
   * 본문(개인 정보가 있을 수 있음)은 넣지 않고 큐 이름과 오류 종류만 보내요.
   */
  @Bean
  MessageRecoverer alertingRecoverer(OpsAlert alert) {
    MessageRecoverer reject = new RejectAndDontRequeueRecoverer();
    return (message, cause) -> {
      String queue = message.getMessageProperties().getConsumerQueue();
      Throwable root = cause;
      while (root.getCause() != null && root.getCause() != root) {
        root = root.getCause();
      }
      alert.send(
          "amqp.dlq:" + queue,
          "받은 메시지를 처리하지 못해 실패 큐로 보냈어요: " + queue,
          root.getClass().getSimpleName() + ": " + root.getMessage());
      reject.recover(message, cause);
    };
  }

  static boolean retryable(Throwable error) {
    for (Throwable cause = error; cause != null; cause = cause.getCause()) {
      if (cause instanceof AmqpRejectAndDontRequeueException) {
        return false;
      }
    }
    return true;
  }
}
