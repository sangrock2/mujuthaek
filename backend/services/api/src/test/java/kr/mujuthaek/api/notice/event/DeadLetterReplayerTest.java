package kr.mujuthaek.api.notice.event;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyBoolean;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.inOrder;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.rabbitmq.client.AMQP;
import com.rabbitmq.client.Channel;
import com.rabbitmq.client.Envelope;
import com.rabbitmq.client.GetResponse;
import com.rabbitmq.client.Return;
import com.rabbitmq.client.ReturnCallback;
import java.util.Map;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.mockito.InOrder;
import org.springframework.amqp.rabbit.connection.Connection;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;

class DeadLetterReplayerTest {

  private final ConnectionFactory factory = mock(ConnectionFactory.class);
  private final Connection connection = mock(Connection.class);
  private final Channel channel = mock(Channel.class);
  private final DeadLetterReplayer replayer = new DeadLetterReplayer(factory);

  @BeforeEach
  void setUp() {
    when(factory.createConnection()).thenReturn(connection);
    when(connection.createChannel(false)).thenReturn(channel);
  }

  private static GetResponse message(long tag, Map<String, Object> headers) {
    AMQP.BasicProperties props = new AMQP.BasicProperties.Builder().headers(headers).build();
    return new GetResponse(
        new Envelope(tag, false, "", ExtractionCompletedListener.DLQ), props, new byte[] {1}, 0);
  }

  @Test
  void 원래_큐로_다시_보내고_브로커_확인_뒤에_지운다() throws Exception {
    when(channel.messageCount(ExtractionCompletedListener.DLQ)).thenReturn(1L);
    when(channel.basicGet(ExtractionCompletedListener.DLQ, false)).thenReturn(message(7, null));

    DeadLetterReplayer.Result result = replayer.replay(10);

    assertThat(result).isEqualTo(new DeadLetterReplayer.Result(1, 0));
    ArgumentCaptor<AMQP.BasicProperties> props =
        ArgumentCaptor.forClass(AMQP.BasicProperties.class);
    InOrder order = inOrder(channel);
    order.verify(channel).confirmSelect();
    order
        .verify(channel)
        .basicPublish(
            eq(""), eq(ExtractionCompletedListener.QUEUE), eq(true), props.capture(), any());
    order.verify(channel).waitForConfirmsOrDie(anyLong());
    order.verify(channel).basicAck(7, false);
    assertThat(props.getValue().getHeaders()).containsEntry(DeadLetterReplayer.REPLAY_HEADER, 1);
  }

  @Test
  void 횟수를_넘긴_메시지는_실패_큐_끝에_남긴다() throws Exception {
    when(channel.messageCount(ExtractionCompletedListener.DLQ)).thenReturn(1L);
    when(channel.basicGet(ExtractionCompletedListener.DLQ, false))
        .thenReturn(message(3, Map.of(DeadLetterReplayer.REPLAY_HEADER, 3)));

    assertThat(replayer.replay(10)).isEqualTo(new DeadLetterReplayer.Result(0, 1));
    verify(channel)
        .basicPublish(eq(""), eq(ExtractionCompletedListener.DLQ), eq(true), any(), any());
    verify(channel, never())
        .basicPublish(eq(""), eq(ExtractionCompletedListener.QUEUE), anyBoolean(), any(), any());
    verify(channel).basicAck(3, false);
  }

  @Test
  void 실행_시점의_큐_길이와_요청_건수_중_작은_만큼만_읽는다() throws Exception {
    when(channel.messageCount(ExtractionCompletedListener.DLQ)).thenReturn(5L);
    when(channel.basicGet(ExtractionCompletedListener.DLQ, false)).thenReturn(message(1, null));

    assertThat(replayer.replay(2).replayed()).isEqualTo(2);
    verify(channel, org.mockito.Mockito.times(2)).basicGet(ExtractionCompletedListener.DLQ, false);
  }

  @Test
  void 받을_큐가_없어_돌아온_메시지는_지우지_않고_멈춘다() throws Exception {
    when(channel.messageCount(ExtractionCompletedListener.DLQ)).thenReturn(2L);
    when(channel.basicGet(ExtractionCompletedListener.DLQ, false)).thenReturn(message(5, null));
    AtomicReference<ReturnCallback> callback = new AtomicReference<>();
    doAnswer(
            invocation -> {
              callback.set(invocation.getArgument(0));
              return null;
            })
        .when(channel)
        .addReturnListener(any(ReturnCallback.class));
    // 브로커는 basic.return을 확인(ack)보다 먼저 보내요
    doAnswer(
            invocation -> {
              callback.get().handle(new Return(312, "NO_ROUTE", "", "", null, new byte[0]));
              return null;
            })
        .when(channel)
        .waitForConfirmsOrDie(anyLong());

    assertThatThrownBy(() -> replayer.replay(10)).isInstanceOf(IllegalStateException.class);
    verify(channel).basicNack(5, false, true);
    verify(channel, never()).basicAck(anyLong(), anyBoolean());
    verify(channel, org.mockito.Mockito.times(1)).basicGet(ExtractionCompletedListener.DLQ, false);
  }

  @Test
  void 큐가_비면_멈춘다() throws Exception {
    when(channel.messageCount(ExtractionCompletedListener.DLQ)).thenReturn(3L);
    when(channel.basicGet(ExtractionCompletedListener.DLQ, false)).thenReturn(null);

    assertThat(replayer.replay(10)).isEqualTo(new DeadLetterReplayer.Result(0, 0));
    verify(channel, never()).basicAck(anyLong(), anyBoolean());
  }
}
