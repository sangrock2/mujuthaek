package kr.mujuthaek.api.notification.service.internal;

import java.time.Clock;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import java.util.stream.Collectors;
import kr.mujuthaek.api.common.event.NoticePublished;
import kr.mujuthaek.api.common.event.NoticeUpdated;
import kr.mujuthaek.api.notice.service.NoticeFollowUpSummary;
import kr.mujuthaek.api.notice.service.NoticeQueryService;
import kr.mujuthaek.api.notice.service.NoticeSummary;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

/**
 * notice의 내부 이벤트(NoticePublished·NoticeUpdated)를 알림 서버로 보낼 notification.requested로 바꿔 아웃박스에 적어요
 * (contracts/schemas/notification-events.draft.md). 공고 저장과 같은 트랜잭션에서 불러요.
 *
 * <ul>
 *   <li>NoticePublished → NEW_NOTICE (관심 조건이 맞는 회원 + 관심 공고로 둔 회원)
 *   <li>NoticeUpdated에 알릴 섹션 → CORRECTED (관심 공고로 둔 회원)
 *   <li>NoticeUpdated에 followUps → FOLLOW_UP (관심 공고로 둔 회원)
 *   <li>NoticeUpdated에 sources(합치기·되돌리기)만 → 보내지 않아요
 * </ul>
 *
 * <p>과거 공고 재처리(reprocess), 숨긴·공개 전 공고, 이미 마감된 공고의 새 소식은 보내지 않아요. 적는 방법은 {@link
 * NotificationRequests}.
 */
@Service
public class NoticeNotificationService {

  static final String TARGET = "NOTICE";
  static final String KIND = "공고";
  static final String FOLLOW_UPS = "followUps";

  /**
   * 정정 알림에 넣을 섹션과 문구 이름 (NoticeUpdated.changedFields). 안내 문구(guidance), 판정용
   * 조건·틀(conditions·judgment), 보류 항목(heldItems)은 사용자가 보는 내용이 아니라 알리지 않아요
   */
  static final Map<String, String> ALERT_LABELS = labels();

  private final NoticeQueryService notices;
  private final RecipientFinder recipients;
  private final NotificationRequests requests;
  private final Clock clock;

  public NoticeNotificationService(
      NoticeQueryService notices,
      RecipientFinder recipients,
      NotificationRequests requests,
      Clock clock) {
    this.notices = notices;
    this.recipients = recipients;
    this.requests = requests;
    this.clock = clock;
  }

  /** 새 공고 → NEW_NOTICE. 보낸 요청 수를 돌려줘요 */
  @Transactional(propagation = Propagation.MANDATORY)
  public int onPublished(NoticePublished event) {
    if (event.reprocess()) {
      return 0;
    }
    Optional<NoticeSummary> found = notices.findSummary(event.noticeId());
    if (found.isEmpty() || !found.get().noticeId().equals(event.noticeId())) {
      return 0; // 숨김·공개 전이거나 이미 다른 공고에 합쳐졌어요
    }
    NoticeSummary n = found.get();
    if ("CLOSED".equals(n.status())) {
      return 0; // 이미 마감된 공고는 새 소식으로 알리지 않아요
    }
    return requests.write(
        "NEW_NOTICE",
        TARGET + ":" + n.noticeId() + ":NEW",
        TARGET,
        n.noticeId(),
        NotificationRequests.noticeLink(n.noticeId(), n.field()),
        "새 " + KIND + ": " + n.title(),
        "관심 조건에 맞는 새 " + KIND + " 소식이에요." + summary(n),
        distinct(
            recipients.forNewNotice(
                n.field(),
                event.regionCodes() == null ? List.of() : event.regionCodes(),
                n.nationwide(),
                n.noticeType()),
            recipients.forFavorite(TARGET, n.noticeId(), "NEW_NOTICE")));
  }

  /** 바뀐 공고 → CORRECTED 또는 FOLLOW_UP. 알릴 것이 없으면 보내지 않아요 */
  @Transactional(propagation = Propagation.MANDATORY)
  public int onUpdated(NoticeUpdated event) {
    if (event.reprocess()) {
      return 0;
    }
    List<String> changed = event.changedFields() == null ? List.of() : event.changedFields();
    String labels =
        changed.stream()
            .map(ALERT_LABELS::get)
            .filter(Objects::nonNull)
            .distinct()
            .collect(Collectors.joining(", "));
    boolean followUp = changed.contains(FOLLOW_UPS);
    if (labels.isEmpty() && !followUp) {
      return 0; // 합치기·되돌리기(sources)나 사용자가 보지 않는 부분만 바뀜
    }
    Optional<NoticeSummary> found = notices.findSummary(event.noticeId());
    if (found.isEmpty()) {
      return 0;
    }
    NoticeSummary n = found.get();
    int sent = 0;
    if (!labels.isEmpty()) {
      sent +=
          requests.write(
              "CORRECTED",
              TARGET + ":" + n.noticeId() + ":CORRECTED:" + n.version(),
              TARGET,
              n.noticeId(),
              NotificationRequests.noticeLink(n.noticeId(), n.field()),
              "정정: " + n.title(),
              "관심 " + KIND + "의 " + labels + " 내용이 바뀌었어요.",
              recipients.forFavorite(TARGET, n.noticeId(), "CORRECTED"));
    }
    if (followUp) {
      sent += followUp(n);
    }
    return sent;
  }

  private int followUp(NoticeSummary n) {
    Optional<NoticeFollowUpSummary> latest = notices.findLatestFollowUp(n.noticeId());
    if (latest.isEmpty()) {
      return 0;
    }
    NoticeFollowUpSummary f = latest.get();
    String when =
        f.postedOn() == null ? "" : " (" + NotificationRequests.monthDay(f.postedOn()) + ")";
    // 같은 글이 새 버전으로 바뀌어도 키가 같아 알림 서버가 한 번만 보내요
    return requests.write(
        "FOLLOW_UP",
        TARGET + ":" + n.noticeId() + ":FOLLOW_UP:" + f.followUpId(),
        TARGET,
        n.noticeId(),
        NotificationRequests.noticeLink(n.noticeId(), n.field()),
        "후속 안내: " + n.title(),
        f.title() == null || f.title().isBlank()
            ? "관심 " + KIND + "에 새 후속 안내" + when + "가 올라왔어요."
            : "관심 " + KIND + "에 '" + f.title() + "'" + when + " 안내가 올라왔어요.",
        recipients.forFavorite(TARGET, n.noticeId(), "FOLLOW_UP"));
  }

  private String summary(NoticeSummary n) {
    StringBuilder sb = new StringBuilder();
    if (n.provider() != null && !n.provider().isBlank()) {
      sb.append(' ').append(n.provider());
    }
    if ("ALWAYS".equals(n.status())) {
      sb.append(sb.isEmpty() ? " " : " · ").append("상시 모집");
    } else if (n.applyEnd() != null && !n.applyEnd().isBefore(LocalDate.now(clock))) {
      sb.append(sb.isEmpty() ? " " : " · ")
          .append(NotificationRequests.monthDay(n.applyEnd()))
          .append(" 마감");
    }
    return sb.toString();
  }

  /** 관심 조건과 관심 공고에 둘 다 걸린 회원은 한 번만 */
  private static List<Recipient> distinct(List<Recipient> first, List<Recipient> second) {
    Set<UUID> seen = new HashSet<>();
    List<Recipient> all = new ArrayList<>();
    for (List<Recipient> list : List.of(first, second)) {
      for (Recipient r : list) {
        if (seen.add(r.userId())) {
          all.add(r);
        }
      }
    }
    return all;
  }

  private static Map<String, String> labels() {
    Map<String, String> m = new LinkedHashMap<>();
    m.put("notice", "기본 정보");
    m.put("locations", "위치");
    m.put("supplyGroups", "공급·가격");
    m.put("schedules", "일정");
    m.put("eligibility", "자격");
    m.put("selectionRules", "선정 방법");
    m.put("requiredDocuments", "제출 서류");
    m.put("applicationWindows", "접수 기간");
    return Collections.unmodifiableMap(m);
  }
}
