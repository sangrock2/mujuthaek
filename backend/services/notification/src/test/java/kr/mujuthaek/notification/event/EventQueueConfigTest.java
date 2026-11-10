package kr.mujuthaek.notification.event;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.amqp.AmqpRejectAndDontRequeueException;
import org.springframework.amqp.rabbit.support.ListenerExecutionFailedException;
import org.springframework.dao.DataAccessResourceFailureException;

class EventQueueConfigTest {

  @Test
  void rejectedMessagesAreNotRetriedButTemporaryErrorsAre() {
    // 리스너 예외는 컨테이너가 ListenerExecutionFailedException으로 감싸서 넘겨요
    var broken =
        new ListenerExecutionFailedException(
            "listener", new AmqpRejectAndDontRequeueException("이벤트 봉투를 읽지 못했어요"));
    var dbDown =
        new ListenerExecutionFailedException(
            "listener", new DataAccessResourceFailureException("연결 끊김"));

    assertThat(EventQueueConfig.retryable(broken)).isFalse();
    assertThat(EventQueueConfig.retryable(dbDown)).isTrue();
  }
}
