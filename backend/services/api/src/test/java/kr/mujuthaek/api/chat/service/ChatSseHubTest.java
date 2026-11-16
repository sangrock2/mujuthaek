package kr.mujuthaek.api.chat.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatCode;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;

import jakarta.servlet.AsyncEvent;
import jakarta.servlet.AsyncListener;
import java.util.UUID;
import java.util.concurrent.Executors;
import java.util.stream.IntStream;
import kr.mujuthaek.api.chat.event.ChatEvent;
import kr.mujuthaek.api.common.exception.CustomException;
import kr.mujuthaek.api.common.exception.ErrorCode;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockAsyncContext;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

/** 방별 연결: 붙이고, 끊긴 연결로 보내거나 하트비트를 보내도 예외가 밖으로 나오지 않아요. 실제 전달은 ChatApiTest에서 봐요. */
class ChatSseHubTest {

  private final ChatSseHub hub = new ChatSseHub();

  @Test
  void roomAndGlobalBudgetsRejectBeforeAddingAnotherConnection() {
    var limited = new ChatSseHub(3, 2);
    UUID room = UUID.randomUUID();
    limited.subscribe(room);
    limited.subscribe(room);
    assertThatThrownBy(() -> limited.subscribe(room))
        .isInstanceOfSatisfying(
            CustomException.class,
            error -> assertThat(error.errorCode()).isEqualTo(ErrorCode.RATE_LIMITED));
    limited.subscribe(UUID.randomUUID());
    assertThatThrownBy(() -> limited.subscribe(UUID.randomUUID()))
        .isInstanceOf(CustomException.class);
    assertThat(limited.connections(room)).isEqualTo(2);
  }

  @Test
  void concurrentConnectionsCannotOverrunTheGlobalBudget() throws Exception {
    var limited = new ChatSseHub(8, 8);
    try (var pool = Executors.newFixedThreadPool(8)) {
      var tasks =
          IntStream.range(0, 64)
              .<java.util.concurrent.Callable<Boolean>>mapToObj(
                  i ->
                      () -> {
                        try {
                          limited.subscribe(UUID.randomUUID());
                          return true;
                        } catch (CustomException error) {
                          assertThat(error.errorCode()).isEqualTo(ErrorCode.RATE_LIMITED);
                          return false;
                        }
                      })
              .toList();
      int joined = 0;
      for (var result : pool.invokeAll(tasks)) if (result.get()) joined++;
      assertThat(joined).isEqualTo(8);
    }
  }

  @Test
  void subscribeJoinsTheRoom() {
    UUID room = UUID.randomUUID();

    hub.subscribe(room);
    hub.subscribe(room);

    assertThat(hub.connections(room)).isEqualTo(2);
    assertThat(hub.connections(UUID.randomUUID())).isZero();
  }

  @Test
  void closedConnectionsDoNotBreakBroadcastOrHeartbeat() {
    UUID room = UUID.randomUUID();
    SseEmitter emitter = hub.subscribe(room);
    emitter.complete();

    assertThatCode(
            () -> {
              hub.broadcast(ChatEvent.deleted(room, UUID.randomUUID()));
              hub.broadcast(ChatEvent.likeUpdated(UUID.randomUUID(), UUID.randomUUID(), 1));
              hub.heartbeat();
            })
        .doesNotThrowAnyException();
  }

  /**
   * 보안 감사 M-4: 스프링은 미리 보낸 내용을 쓴 뒤에 완료·오류 알림을 등록해서, 그 사이 연결이 끊기면 알림이 오지 않아 자리가 영영 남았어요. 알림 없이 끝난 연결도
   * 보내기·하트비트가 실패하면 자리를 돌려줘야 해요.
   */
  @Test
  void connectionsEndedWithoutCallbacksGiveTheirSlotBackOnTheNextSend() {
    var limited = new ChatSseHub(1, 1);
    UUID room = UUID.randomUUID();
    SseEmitter emitter = limited.subscribe(room);
    emitter.complete(); // 스프링에 넘기기 전에 끝남: 등록한 알림이 불리지 않아요
    assertThat(limited.connections(room)).isEqualTo(1);

    limited.heartbeat();

    assertThat(limited.connections(room)).isZero();
    assertThat(limited.totalConnections()).isZero();
    limited.subscribe(UUID.randomUUID());
  }

  @Test
  void releaseGivesTheSlotBackOnlyOnce() {
    var limited = new ChatSseHub(2, 2);
    UUID room = UUID.randomUUID();
    SseEmitter first = limited.subscribe(room);
    limited.subscribe(room);

    limited.release(first);
    limited.release(first);
    first.complete();

    assertThat(limited.totalConnections()).isEqualTo(1);
    limited.subscribe(room);
    assertThatThrownBy(() -> limited.subscribe(room)).isInstanceOf(CustomException.class);
  }

  @Test
  void connectionsOlderThanTheTimeoutAreSweptEvenIfNoCallbackArrives() {
    long[] now = {0};
    var limited = new ChatSseHub(1, 1, () -> now[0]);
    UUID room = UUID.randomUUID();
    limited.subscribe(room);

    now[0] = ChatSseHub.STALE_AFTER_MS - 1;
    limited.heartbeat();
    assertThat(limited.connections(room)).isEqualTo(1);

    now[0] = ChatSseHub.STALE_AFTER_MS;
    limited.heartbeat();
    assertThat(limited.connections(room)).isZero();
    limited.subscribe(room);
  }

  /** 연결이 타임아웃(30분)되면 정상으로 닫아요. 타임아웃 오류(503)로 끝나면 「처리하지 못한 오류」 알림이 가요. 브라우저는 다시 붙어요. */
  @Test
  void timedOutConnectionClosesNormallyInsteadOfATimeoutError() throws Exception {
    UUID room = UUID.randomUUID();
    var limited = new ChatSseHub(1, 1);
    MockMvc mvc = MockMvcBuilders.standaloneSetup(new StreamController(limited)).build();
    MvcResult stream =
        mvc.perform(get("/rooms/{id}/stream", room))
            .andExpect(request().asyncStarted())
            .andReturn();
    assertThat(limited.connections(room)).isEqualTo(1);
    assertThatThrownBy(() -> limited.subscribe(UUID.randomUUID()))
        .isInstanceOf(CustomException.class);

    // 서블릿 컨테이너가 비동기 타임아웃을 알리는 것처럼
    MockAsyncContext async = (MockAsyncContext) stream.getRequest().getAsyncContext();
    for (AsyncListener listener : async.getListeners()) {
      listener.onTimeout(new AsyncEvent(async));
    }

    // 정상으로 닫히면 결과가 비어 있어요 (그냥 두면 AsyncRequestTimeoutException이 결과가 돼요)
    assertThat(stream.getAsyncResult()).isNull();
    assertThat(limited.connections(room)).isZero();
    // 타임아웃·완료가 겹쳐도 예산을 두 번 돌려주지 않고, 다음 연결 하나만 허용해요.
    for (AsyncListener listener : async.getListeners()) listener.onComplete(new AsyncEvent(async));
    limited.subscribe(UUID.randomUUID());
    assertThatThrownBy(() -> limited.subscribe(UUID.randomUUID()))
        .isInstanceOf(CustomException.class);
  }

  @RestController
  record StreamController(ChatSseHub hub) {
    @GetMapping("/rooms/{id}/stream")
    SseEmitter stream(@PathVariable UUID id) {
      return hub.subscribe(id);
    }
  }
}
