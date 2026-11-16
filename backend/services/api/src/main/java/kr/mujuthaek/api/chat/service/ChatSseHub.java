package kr.mujuthaek.api.chat.service;

import java.io.IOException;
import java.time.Duration;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.function.LongSupplier;
import kr.mujuthaek.api.chat.event.ChatEvent;
import kr.mujuthaek.api.common.exception.CustomException;
import kr.mujuthaek.api.common.exception.ErrorCode;
import org.springframework.http.MediaType;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

/**
 * 채팅방별 SSE 연결. 서버 메모리에 두어서 서버 한 대 기준이에요 (여러 대가 되면 RabbitMQ 팬아웃으로 서버끼리 전달해요, 아직 안 만듦).
 *
 * <p>끊긴 연결은 보내다 실패하거나 타임아웃·완료되면 지워요. 브라우저 EventSource는 끊기면 알아서 다시 붙어요.
 *
 * <p>자리(연결 예산)는 스프링의 완료·오류·타임아웃 알림만 믿지 않고, 보내기·하트비트가 실패해도, 열어 둔 시간이 지나도 돌려줘요. 스프링은 미리 보낸 내용(놓친 메시지
 * 재전송)을 먼저 쓴 뒤에 알림을 등록해서, 그 사이 연결이 끊기면 알림이 오지 않아 자리가 영영 남았어요. 로그인 없이 되풀이하면 모든 방의 실시간 연결을 재시작 전까지 막을
 * 수 있었어요(2026-11-16 보안 감사 M-4).
 */
@Component
public class ChatSseHub {

  /** 연결 하나를 열어 두는 시간. 이 값이 그 요청의 비동기 타임아웃이 돼요. */
  static final long TIMEOUT_MS = Duration.ofMinutes(30).toMillis();

  /** 타임아웃 알림이 오지 않은 연결도 이만큼 지나면 자리를 돌려줘요. */
  static final long STALE_AFTER_MS = TIMEOUT_MS + Duration.ofMinutes(1).toMillis();

  /** 자리 하나: 한 번만 돌려주는 leave와 붙은 시각. */
  private record Slot(Runnable leave, long joinedAtMs) {}

  private final Map<UUID, Set<SseEmitter>> rooms = new ConcurrentHashMap<>();
  private final Map<SseEmitter, Slot> slots = new ConcurrentHashMap<>();
  private final int maxConnections;
  private final int maxRoomConnections;
  private final LongSupplier clockMs;
  private int totalConnections;

  public ChatSseHub() {
    this(128, 32);
  }

  ChatSseHub(int maxConnections, int maxRoomConnections) {
    this(maxConnections, maxRoomConnections, System::currentTimeMillis);
  }

  ChatSseHub(int maxConnections, int maxRoomConnections, LongSupplier clockMs) {
    this.maxConnections = maxConnections;
    this.maxRoomConnections = maxRoomConnections;
    this.clockMs = clockMs;
  }

  /** 방에 연결을 하나 붙여요. 붙자마자 주석 한 줄을 보내 프록시·브라우저가 연결을 바로 열게 해요. */
  public SseEmitter subscribe(UUID noticeId) {
    SseEmitter emitter = new SseEmitter(TIMEOUT_MS);
    synchronized (rooms) {
      Set<SseEmitter> joined = rooms.get(noticeId);
      if (totalConnections >= maxConnections
          || (joined != null && joined.size() >= maxRoomConnections)) {
        throw new CustomException(ErrorCode.RATE_LIMITED);
      }
      rooms.computeIfAbsent(noticeId, id -> ConcurrentHashMap.newKeySet()).add(emitter);
      totalConnections++;
    }
    AtomicBoolean left = new AtomicBoolean();
    Runnable leave =
        () -> {
          if (!left.compareAndSet(false, true)) return;
          slots.remove(emitter);
          synchronized (rooms) {
            rooms.computeIfPresent(
                noticeId,
                (id, room) -> {
                  room.remove(emitter);
                  return room.isEmpty() ? null : room;
                });
            totalConnections--;
          }
        };
    slots.put(emitter, new Slot(leave, clockMs.getAsLong()));
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
    } catch (IOException | IllegalStateException e) {
      leave.run();
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
      drop(emitter, e); // 끊긴 연결 정리
    }
  }

  /** 이 연결의 자리를 돌려줘요 (여러 번 불러도 한 번만). 구독을 만든 뒤 컨트롤러에 넘기기 전에 실패하면 스프링이 이 연결을 모르니 여기서 돌려줘야 해요. */
  public void release(SseEmitter emitter) {
    Slot slot = slots.get(emitter);
    if (slot != null) {
      slot.leave().run();
    }
  }

  /** 25초마다 주석 한 줄: 프록시·로드밸런서가 조용한 연결을 끊지 않게 해요. 화면은 무시해요. 열어 둔 시간이 지난 연결도 정리해요. */
  @Scheduled(fixedRate = 25_000)
  void heartbeat() {
    long now = clockMs.getAsLong();
    slots.forEach(
        (emitter, slot) -> {
          if (now - slot.joinedAtMs() >= STALE_AFTER_MS) {
            slot.leave().run();
            try {
              emitter.complete();
            } catch (IllegalStateException alreadyDone) {
              // 이미 끝난 연결
            }
          }
        });
    rooms
        .values()
        .forEach(
            room ->
                room.forEach(
                    emitter -> {
                      try {
                        emitter.send(SseEmitter.event().comment("ping"));
                      } catch (IOException | IllegalStateException e) {
                        drop(emitter, e);
                      }
                    }));
  }

  private void drop(SseEmitter emitter, Exception error) {
    release(emitter);
    try {
      emitter.completeWithError(error);
    } catch (IllegalStateException alreadyDone) {
      // 이미 끝난 연결
    }
  }

  /** 방에 붙은 연결 수 (테스트·점검용). */
  int connections(UUID noticeId) {
    Set<SseEmitter> room = rooms.get(noticeId);
    return room == null ? 0 : room.size();
  }

  /** 전체 연결 수 (테스트·점검용). */
  int totalConnections() {
    synchronized (rooms) {
      return totalConnections;
    }
  }
}
