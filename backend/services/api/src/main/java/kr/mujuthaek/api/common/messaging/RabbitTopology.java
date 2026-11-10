package kr.mujuthaek.api.common.messaging;

import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.Declarables;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.amqp.core.TopicExchange;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * 파이썬 프로그램과 같은 exchange 이름이에요 (libs/python-platform outbox, extraction worker).
 *
 * <p>큐마다 같은 이름 + ".dlq"인 실패 큐를 두고, 받다가 실패한 메시지는 {@link #DLX}로 보내요. 모듈은 {@link #queue}로 자기 큐를 선언해요.
 */
@Configuration
public class RabbitTopology {

  public static final String EVENTS = "mujuthaek.events";
  public static final String DLX = "mujuthaek.dlx";

  @Bean
  TopicExchange eventsExchange() {
    return new TopicExchange(EVENTS, true, false);
  }

  @Bean
  TopicExchange deadLetterExchange() {
    return new TopicExchange(DLX, true, false);
  }

  /** routingKey로 오는 이벤트를 받을 큐와 실패 큐, 두 바인딩. */
  public static Declarables queue(String name, String routingKey) {
    Queue queue = QueueBuilder.durable(name).deadLetterExchange(DLX).build();
    Queue dlq = QueueBuilder.durable(name + ".dlq").build();
    Binding binding =
        BindingBuilder.bind(queue).to(new TopicExchange(EVENTS, true, false)).with(routingKey);
    Binding dlqBinding =
        BindingBuilder.bind(dlq).to(new TopicExchange(DLX, true, false)).with(routingKey);
    return new Declarables(queue, dlq, binding, dlqBinding);
  }
}
