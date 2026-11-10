package kr.mujuthaek.api.area.event;

import java.time.LocalDate;
import kr.mujuthaek.api.area.domain.AreaLoadRequest;
import kr.mujuthaek.api.area.domain.AreaSource;
import kr.mujuthaek.api.area.repository.AreaLoadQueue;
import kr.mujuthaek.api.area.service.AreaLoadWorker;
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

/**
 * collector가 원천 파일을 S3 area/에 올리고 보내는 area.source.ready를 받아 적재 대기열에 넣어요
 * (contracts/events/area.source.ready.v1.json).
 *
 * <p>적재는 여기서 하지 않아요. 큰 파일은 몇십 분 걸려서, 받는 자리에서 적재하면 RabbitMQ consumer_timeout(30분)을 넘겨 채널이 닫히고 수신기가
 * 멈췄어요. 그래서 PENDING 요청만 남기고 바로 끝내고(ack), {@link AreaLoadWorker}가 하나씩 꺼내 적재해요.
 *
 * <ul>
 *   <li>같은 파일(원천·범위·지문)이 이미 성공했으면 SKIPPED로 남기고, 기다리거나 도는 중이면 넘어가요
 *   <li>실패한 파일을 다시 올리면 다시 기다리게 넣어요. 그래서 eventId 처리 기록(processed_events) 대신 파일 기준으로 걸러요 (같은 파일이면
 *       eventId도 같아요)
 *   <li>봉투·payload를 읽지 못하면 다시 해도 같아서 바로 실패 큐(.dlq)로 가요
 * </ul>
 */
@Component
class AreaSourceReadyListener {

  private static final Logger log = LoggerFactory.getLogger(AreaSourceReadyListener.class);

  static final String QUEUE = "mujuthaek.area.source-ready";
  static final String EVENT_TYPE = "area.source.ready";

  private final EventInbox inbox;
  private final AreaLoadQueue queue;
  private final AreaLoadWorker worker;

  AreaSourceReadyListener(EventInbox inbox, AreaLoadQueue queue, AreaLoadWorker worker) {
    this.inbox = inbox;
    this.queue = queue;
    this.worker = worker;
  }

  @RabbitListener(queues = QUEUE)
  void on(Message message) {
    AreaSourceReady event = inbox.readPayload(message, EVENT_TYPE, 1, AreaSourceReady.class);
    AreaLoadRequest request;
    try {
      request =
          new AreaLoadRequest(
              event.source(),
              event.scope(),
              event.s3Key(),
              event.sha256(),
              event.dataDate(),
              false);
    } catch (IllegalArgumentException | NullPointerException e) {
      throw new AmqpRejectAndDontRequeueException(
          "area.source.ready 내용이 맞지 않아요: " + e.getMessage(), e);
    }
    AreaLoadQueue.Requested result = queue.request(request);
    log.info("area 적재 요청 {} {}: {}", request.source(), request.scope(), result);
    if (result == AreaLoadQueue.Requested.QUEUED) {
      worker.wake();
    }
  }

  /** area.source.ready의 payload. fileName·rows는 기록용이라 받지 않아요. */
  record AreaSourceReady(
      AreaSource source, String scope, String s3Key, String sha256, LocalDate dataDate) {}

  @Configuration
  static class Queues {

    @Bean
    Declarables areaSourceReadyQueue() {
      return RabbitTopology.queue(QUEUE, EVENT_TYPE);
    }
  }
}
