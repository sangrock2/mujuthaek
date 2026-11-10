package kr.mujuthaek.api.notice.event;

import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.nio.charset.StandardCharsets;
import java.util.function.BiConsumer;
import kr.mujuthaek.api.common.messaging.EventInbox;
import kr.mujuthaek.api.notice.domain.IngestionOutcome;
import kr.mujuthaek.api.notice.mapper.ExtractionEvent;
import kr.mujuthaek.api.notice.service.internal.NoticeIngestionService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.amqp.AmqpRejectAndDontRequeueException;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageProperties;

class ExtractionCompletedListenerTest {

  private final EventInbox inbox = mock(EventInbox.class);
  private final NoticeIngestionService ingestion = mock(NoticeIngestionService.class);
  private final ExtractionCompletedListener listener =
      new ExtractionCompletedListener(inbox, ingestion);

  @BeforeEach
  @SuppressWarnings("unchecked")
  void inboxRunsTheHandler() {
    doAnswer(
            call -> {
              ((BiConsumer<Object, Object>) call.getArgument(4)).accept(null, null);
              return null;
            })
        .when(inbox)
        .handleOnceWithEnvelope(any(), eq("extraction.completed"), anyInt(), any(), any());
  }

  private static Message message(String body) {
    return new Message(body.getBytes(StandardCharsets.UTF_8), new MessageProperties());
  }

  @Test
  void 받은_봉투_글자_그대로_서비스에_넘긴다() {
    when(ingestion.apply("{\"a\":1}")).thenReturn(IngestionOutcome.PUBLISHED);

    listener.on(message("{\"a\":1}"));

    verify(ingestion).apply("{\"a\":1}");
  }

  @Test
  void 계약_오류는_다시_시도하지_않고_실패_큐로_보낸다() {
    when(ingestion.apply(anyString()))
        .thenThrow(new ExtractionEvent.InvalidEventException("형식 오류"));

    assertThatThrownBy(() -> listener.on(message("{}")))
        .isInstanceOf(AmqpRejectAndDontRequeueException.class);
  }

  @Test
  void 그_밖의_오류는_그대로_던져_재시도에_맡긴다() {
    when(ingestion.apply(anyString())).thenThrow(new IllegalStateException("DB 일시 오류"));

    assertThatThrownBy(() -> listener.on(message("{}"))).isInstanceOf(IllegalStateException.class);
  }
}
