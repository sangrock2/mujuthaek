package kr.mujuthaek.api.notification.service.internal;

import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import kr.mujuthaek.api.common.id.UuidV7;
import kr.mujuthaek.api.common.messaging.Outbox;
import kr.mujuthaek.api.common.text.ScreenPaths;
import kr.mujuthaek.api.notification.repository.InboxRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

/**
 * 알림 하나를 받는 사람들에게 남기고 보내요. 부르는 쪽(공고·정책 저장, 마감 확인)의 트랜잭션 안에서 써요.
 *
 * <ol>
 *   <li>알림함: 받는 사람마다 한 줄 (알림 설정·기기와 상관없이, 같은 dedupKey면 한 번)
 *   <li>웹 푸시 기기: 회원마다 최근 5대 (recipients[].push, contracts/schemas/web-push.draft.md 3장)
 *   <li>notification.requested를 아웃박스에 (contracts/schemas/notification-events.draft.md). 이메일도 기기도 없는
 *       회원은 알림 서버가 할 일이 없어서 빼요. 한 요청에 500명까지라 넘으면 나눠 적어요
 * </ol>
 *
 * <p>누구에게 보낼지(관심 조건·종류별 켬·끔)는 받는 사람을 고를 때 이미 정했어요. 500명마다 기기를 한 번 조회해요.
 */
@Component
public class NotificationRequests {

  private static final Logger log = LoggerFactory.getLogger(NotificationRequests.class);

  static final String EVENT_TYPE = "notification.requested";
  static final int MAX_RECIPIENTS = 500;

  private final Outbox outbox;
  private final PushDeviceFinder push;
  private final InboxRepository inbox;
  private final Clock clock;

  public NotificationRequests(
      Outbox outbox, PushDeviceFinder push, InboxRepository inbox, Clock clock) {
    this.outbox = outbox;
    this.push = push;
    this.inbox = inbox;
    this.clock = clock;
  }

  /** 적은 요청 수를 돌려줘요. 받는 사람이 없거나 모두 알림함에만 남기면 0 */
  int write(
      String type,
      String dedupKey,
      String targetType,
      UUID targetId,
      String title,
      String body,
      List<Recipient> to) {
    return write(
        type, dedupKey, targetType, targetId, linkPath(targetType, targetId), title, body, to);
  }

  /** 누르면 갈 화면({@code linkPath})을 따로 정할 때 (사업공간 공고처럼 대상 종류만으로 정할 수 없을 때) */
  int write(
      String type,
      String dedupKey,
      String targetType,
      UUID targetId,
      String linkPath,
      String title,
      String body,
      List<Recipient> to) {
    if (to.isEmpty()) {
      log.debug("받을 회원이 없어 알림 요청을 만들지 않아요: type={}, targetId={}", type, targetId);
      return 0;
    }
    Instant now = clock.instant();
    int sent = 0;
    int withPush = 0;
    int stored = 0;
    for (int from = 0; from < to.size(); from += MAX_RECIPIENTS) {
      List<Recipient> chunk = to.subList(from, Math.min(from + MAX_RECIPIENTS, to.size()));
      // 알림함 줄 ID를 요청에도 실어요: 푸시를 받은 기기가 「떴어요·눌렀어요」를 이 ID로 알려 줘요
      Map<UUID, UUID> inboxIds = new LinkedHashMap<>();
      chunk.forEach(r -> inboxIds.putIfAbsent(r.userId(), UuidV7.next()));
      stored +=
          inbox.addAll(
              chunk.stream()
                  .map(
                      r ->
                          new InboxRepository.NewEntry(
                              inboxIds.get(r.userId()),
                              r.userId(),
                              type,
                              targetType,
                              targetId,
                              title,
                              body,
                              linkPath,
                              dedupKey,
                              now))
                  .toList());
      Map<UUID, List<PushDevice>> devices =
          push.latest(
              chunk.stream().filter(Recipient::pushEnabled).map(Recipient::userId).toList());
      withPush += devices.size();
      List<Map<String, Object>> recipients =
          chunk.stream()
              .map(
                  r ->
                      recipient(
                          r,
                          inboxIds.get(r.userId()),
                          r.pushEnabled() ? devices.get(r.userId()) : null))
              .filter(m -> m.get("email") != null || m.get("push") != null)
              .toList();
      if (recipients.isEmpty()) {
        continue; // 모두 알림함에만 (기기·이메일 없음 또는 이 종류를 끔)
      }
      if (targetType == null) {
        continue; // 가리킬 대상이 없는 알림(일반 제보 답변)은 알림함에만. 알림 서버 요청은 대상이 있어야 해요
      }
      Map<String, Object> payload = new LinkedHashMap<>();
      payload.put("type", type);
      payload.put("dedupKey", dedupKey);
      payload.put("target", Map.of("type", targetType, "id", targetId));
      payload.put("title", title);
      payload.put("body", body);
      payload.put("linkPath", linkPath);
      payload.put("recipients", recipients);
      outbox.add(EVENT_TYPE, 1, payload);
      sent++;
    }
    log.info(
        "알림을 남기고 요청을 적음: type={}, targetId={}, 받는 사람={}, 알림함 새 줄={}, 푸시 기기 있는 사람={}, 요청={}",
        type,
        targetId,
        to.size(),
        stored,
        withPush,
        sent);
    return sent;
  }

  private static Map<String, Object> recipient(
      Recipient r, UUID inboxId, List<PushDevice> devices) {
    Map<String, Object> m = new LinkedHashMap<>();
    m.put("userId", r.userId());
    m.put("inboxId", inboxId);
    m.put("email", r.email());
    m.put("quietEnabled", r.quietEnabled());
    m.put(
        "push",
        devices == null || devices.isEmpty()
            ? null
            : devices.stream().map(NotificationRequests::device).toList());
    return m;
  }

  private static Map<String, String> device(PushDevice d) {
    Map<String, String> m = new LinkedHashMap<>();
    m.put("endpoint", d.endpoint());
    m.put("p256dh", d.p256dh());
    m.put("auth", d.auth());
    return m;
  }

  /**
   * 계약의 target.type: 창업지원 사업·사업공간 모집은 분야 이름 그대로(notice.policy_judgments, ID = rawPolicyId), 지원 정책은
   * BENEFIT (benefits)
   */
  static String targetType(String field) {
    return switch (field) {
      case "STARTUP_SUPPORT", "SPACE_RECRUITMENT" -> field;
      default -> "BENEFIT";
    };
  }

  /** 누르면 갈 PWA 화면 ({@link ScreenPaths#of}) */
  static String linkPath(String targetType, UUID id) {
    return ScreenPaths.of(targetType, id);
  }

  /** 공고 화면 ({@link ScreenPaths#notice}) */
  static String noticeLink(UUID noticeId, String field) {
    return ScreenPaths.notice(noticeId, field);
  }

  /** 알림 문구의 {종류} */
  static String kind(String field) {
    return switch (field) {
      case "STARTUP_SUPPORT" -> "창업지원";
      case "SPACE_RECRUITMENT" -> "사업공간 모집";
      default -> "지원 정책";
    };
  }

  /** 문구의 날짜 (M월 d일) */
  static String monthDay(LocalDate date) {
    return date.getMonthValue() + "월 " + date.getDayOfMonth() + "일";
  }
}
