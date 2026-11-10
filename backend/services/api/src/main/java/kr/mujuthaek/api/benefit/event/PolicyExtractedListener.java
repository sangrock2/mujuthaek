package kr.mujuthaek.api.benefit.event;

import java.nio.charset.StandardCharsets;
import kr.mujuthaek.api.benefit.mapper.PolicyExtractedEvent;
import kr.mujuthaek.api.benefit.service.internal.BenefitIngestionService;
import kr.mujuthaek.api.common.messaging.EventInbox;
import kr.mujuthaek.api.common.messaging.RabbitTopology;
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
 * extraction이 보내는 policy.extracted를 받아 혜택으로 저장해요 (contracts/events/policy.extracted.v1.json).
 *
 * <p>큐 mujuthaek.policy.extracted(+ .dlq)는 api가 만들어요. 같은 eventId는 한 번만 처리해요. 계약에 맞지 않는 메시지는 바로 실패
 * 큐로 보내요.
 */
@Component
class PolicyExtractedListener {

  private static final Logger log = LoggerFactory.getLogger(PolicyExtractedListener.class);

  static final String QUEUE = "mujuthaek.policy.extracted";

  private final EventInbox inbox;
  private final BenefitIngestionService ingestion;

  PolicyExtractedListener(EventInbox inbox, BenefitIngestionService ingestion) {
    this.inbox = inbox;
    this.ingestion = ingestion;
  }

  @RabbitListener(queues = QUEUE)
  void on(Message message) {
    inbox.handleOnceWithEnvelope(
        message,
        PolicyExtractedEvent.EVENT_TYPE,
        PolicyExtractedEvent.SCHEMA_VERSION,
        JsonNode.class,
        (envelope, payload) -> apply(message));
  }

  /** 계약 검사는 봉투 전체로 해서 받은 글자 그대로 넘겨요. */
  private void apply(Message message) {
    try {
      ingestion.apply(new String(message.getBody(), StandardCharsets.UTF_8));
    } catch (PolicyExtractedEvent.InvalidEventException e) {
      log.warn("계약에 맞지 않는 policy.extracted라 실패 큐로 보내요: {}", e.getMessage());
      throw new AmqpRejectAndDontRequeueException(e.getMessage(), e);
    }
  }

  @Configuration
  static class Queues {

    @Bean
    Declarables policyExtractedQueue() {
      return RabbitTopology.queue(QUEUE, PolicyExtractedEvent.EVENT_TYPE);
    }
  }
}
