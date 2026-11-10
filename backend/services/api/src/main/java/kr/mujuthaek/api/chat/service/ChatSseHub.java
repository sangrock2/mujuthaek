package kr.mujuthaek.api.chat.service;

import java.io.IOException;
import java.time.Duration;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import kr.mujuthaek.api.chat.event.ChatEvent;
import org.springframework.http.MediaType;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

/**
 * 채팅방별 SSE 연결. 서버 메모리에 두어서 서버 한 대 기준이에요 (여러 대가 되면 RabbitMQ 팬아웃으로 서버끼리 전달해요, 아직 안 만듦).
 *
 * <p>끊긴 연결은 보내다 실패하거나 타임아웃·완료되면 지워요. 브라우저 EventSource는 끊기면 알아서 다시 붙어요.
 */
@Component
public class ChatSseHub {

  /** 연결 하나를 열어 두는 시간. 이 값이 그 요청의 비동기 타임아웃이 돼요. */
  static final long TIMEOUT_MS = Duration.ofMinutes(30).toMillis();

  private final Map<UUID, Set<SseEmitter>> rooms = new ConcurrentHashMap<>();

  /** 방에 연결을 하나 붙여요. 붙자마자 주석 한 줄을 보내 프록시·브라우저가 연결을 바로 열게 해요. */
  public SseEmitter subscribe(UUID noticeId) {
    SseEmitter emitter = new SseEmitter(TIMEOUT_MS);
    rooms.compute(
        noticeId,
        (id, room) -> {
          Set<SseEmitter> joined = room == null ? ConcurrentHashMap.newKeySet() : room;
          joined.add(emitter);
          return joined;
        });
    Runnable leave =
        () ->
            rooms.computeIfPresent(
                noticeId,
                (id, room) -> {
                  room.remove(emitter);
                  return room.isEmpty() ? null : room;
                });
    emitter.onCompletion(leave);
    // 타임아웃이면 정상으로 닫아요. 그냥 두면 스프링이 타임아웃 오류(503)로 끝내 「처리하지 못한 오류」 알림이 가요.
    // 브라우저 EventSource는 끝난 연결에 다시 붙고, Last-Event-ID로 놓친 메시지부터 받아요
    emitter.onTimeout(
        () -> {
          leave.run();
          emitter.complete();
        });
    emitter.onError(error -> leave.run());
    try {
      emitter.send(SseEmitter.event().comment("connected"));
    } catch (IOException e) {
      emitter.completeWithError(e);
    }
    return emitter;
  }

  /** 방의 모든 연결로 보내요. */
  public void broadcast(ChatEvent event) {
    Set<SseEmitter> room = rooms.get(event.noticeId());
    if (room == null) {
      return;
    }
    for (SseEmitter emitter : room) {
      send(emitter, event);
    }
  }

  /** 연결 하나로 보내요 (재연결 때 놓친 메시지). */
  public void send(SseEmitter emitter, ChatEvent event) {
    SseEmitter.SseEventBuilder sse =
        SseEmitter.event().name(event.name()).data(event.data(), MediaType.APPLICATION_JSON);
    if (event.messageId() != null) {
      sse.id(event.messageId().toString());
    }
    try {
      emitter.send(sse);
    } catch (IOException | IllegalStateException e) {
      emitter.completeWithError(e); // 끊긴 연결 정리
    }
  }

  /** 25초마다 주석 한 줄: 프록시·로드밸런서가 조용한 연결을 끊지 않게 해요. 화면은 무시해요. */
  @Scheduled(fixedRate = 25_000)
  void heartbeat() {
    rooms
        .values()
        .forEach(
            room ->
                room.forEach(
                    emitter -> {
                      try {
                        emitter.send(SseEmitter.event().comment("ping"));
                      } catch (IOException | IllegalStateException e) {
                        emitter.completeWithError(e);
                      }
                    }));
  }

  /** 방에 붙은 연결 수 (테스트·점검용). */
  int connections(UUID noticeId) {
    Set<SseEmitter> room = rooms.get(noticeId);
    return room == null ? 0 : room.size();
  }
}
