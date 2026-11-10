package kr.mujuthaek.api.notice.event;

import java.nio.charset.StandardCharsets;
import kr.mujuthaek.api.common.messaging.EventInbox;
import kr.mujuthaek.api.common.messaging.RabbitTopology;
import kr.mujuthaek.api.notice.mapper.ExtractionEvent;
import kr.mujuthaek.api.notice.service.internal.NoticeIngestionService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.amqp.AmqpRejectAndDontRequeueException;
import org.springframework.amqp.core.Declarables;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.stereotype.Component;
import tools.jackson.databind.JsonNode;

/**
 * extraction이 보내는 extraction.completed를 받아 공고로 반영해요
 * (contracts/events/extraction.completed.v1.json).
 *
 * <p>큐 mujuthaek.extraction.completed(+ .dlq)는 api가 만들어요. 같은 eventId는 한 번만 처리해요. 계약에 맞지 않는 메시지는 다시
 * 받아도 같은 결과라 바로 실패 큐로 보내고, 저장 중 예외(DB 일시 오류 등)는 다시 시도한 뒤 실패 큐로 가요.
 */
@Component
class ExtractionCompletedListener {

  private static final Logger log = LoggerFactory.getLogger(ExtractionCompletedListener.class);

  static final String QUEUE = "mujuthaek.extraction.completed";
  static final String EVENT_TYPE = "extraction.completed";
  static final String DLQ = QUEUE + ".dlq";

  private final EventInbox inbox;
  private final NoticeIngestionService ingestion;

  ExtractionCompletedListener(EventInbox inbox, NoticeIngestionService ingestion) {
    this.inbox = inbox;
    this.ingestion = ingestion;
  }

  @RabbitListener(queues = QUEUE)
  void on(Message message) {
    inbox.handleOnceWithEnvelope(
        message,
        EVENT_TYPE,
        ExtractionEvent.SCHEMA_VERSION,
        JsonNode.class,
        (envelope, payload) -> apply(message));
  }

  /** 계약 검사는 봉투 전체(eventId·occurredAt 포함)로 해서 받은 글자 그대로 넘겨요. */
  private void apply(Message message) {
    try {
      ingestion.apply(new String(message.getBody(), StandardCharsets.UTF_8));
    } catch (ExtractionEvent.InvalidEventException e) {
      log.warn("계약에 맞지 않는 extraction.completed라 실패 큐로 보내요: {}", e.getMessage());
      throw new AmqpRejectAndDontRequeueException(e.getMessage(), e);
    }
  }

  @Configuration
  static class Queues {

    @Bean
    Declarables extractionCompletedQueue() {
      return RabbitTopology.queue(QUEUE, EVENT_TYPE);
    }
  }
}
