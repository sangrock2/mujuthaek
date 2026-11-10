package kr.mujuthaek.api.chat.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatCode;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;

import jakarta.servlet.AsyncEvent;
import jakarta.servlet.AsyncListener;
import java.util.UUID;
import kr.mujuthaek.api.chat.event.ChatEvent;
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

  /** 연결이 타임아웃(30분)되면 정상으로 닫아요. 타임아웃 오류(503)로 끝나면 「처리하지 못한 오류」 알림이 가요. 브라우저는 다시 붙어요. */
  @Test
  void timedOutConnectionClosesNormallyInsteadOfATimeoutError() throws Exception {
    UUID room = UUID.randomUUID();
    MockMvc mvc = MockMvcBuilders.standaloneSetup(new StreamController(hub)).build();
    MvcResult stream =
        mvc.perform(get("/rooms/{id}/stream", room))
            .andExpect(request().asyncStarted())
            .andReturn();
    assertThat(hub.connections(room)).isEqualTo(1);

    // 서블릿 컨테이너가 비동기 타임아웃을 알리는 것처럼
    MockAsyncContext async = (MockAsyncContext) stream.getRequest().getAsyncContext();
    for (AsyncListener listener : async.getListeners()) {
      listener.onTimeout(new AsyncEvent(async));
    }

    // 정상으로 닫히면 결과가 비어 있어요 (그냥 두면 AsyncRequestTimeoutException이 결과가 돼요)
    assertThat(stream.getAsyncResult()).isNull();
    assertThat(hub.connections(room)).isZero();
  }

  @RestController
  record StreamController(ChatSseHub hub) {
    @GetMapping("/rooms/{id}/stream")
    SseEmitter stream(@PathVariable UUID id) {
      return hub.subscribe(id);
    }
  }
}
