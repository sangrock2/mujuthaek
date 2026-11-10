package kr.mujuthaek.notification.notification;

import java.time.Clock;
import java.util.List;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import kr.mujuthaek.notification.delivery.DeliveryRepository;
import kr.mujuthaek.notification.delivery.DeliverySchedule;
import kr.mujuthaek.notification.delivery.DigestCadence;
import kr.mujuthaek.notification.delivery.NotificationChannel;
import kr.mujuthaek.notification.support.UuidV7;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

/**
 * notification.requested를 받아 회원마다·채널마다 발송 줄(deliveries)을 만들어요. 실제 발송은 DeliveryWorker가 해요.
 *
 * <p>받을 사람과 받을 주소는 api가 정해서 보내요. 여기서는 요청에 그 채널 주소가 있으면 줄을 만들고, 보낼 시각만 정해요.
 */
@Service
public class NotificationService {

  private static final Logger log = LoggerFactory.getLogger(NotificationService.class);

  private final DeliveryRepository deliveries;
  private final DeliverySchedule schedule;
  private final List<NotificationChannel> channels;
  private final UserDataCleaner users;
  private final Clock clock;

  public NotificationService(
      DeliveryRepository deliveries,
      DeliverySchedule schedule,
      List<NotificationChannel> channels,
      UserDataCleaner users,
      Clock clock) {
    this.deliveries = deliveries;
    this.schedule = schedule;
    this.channels = channels;
    this.users = users;
    this.clock = clock;
  }

  /** 이벤트 기록(processed_events)과 같은 트랜잭션에서 불러요. 새로 만든 발송 줄 수를 돌려줘요 */
  @Transactional(propagation = Propagation.MANDATORY)
  public int handle(NotificationRequest request) {
    request.validate();
    Set<UUID> withdrawn =
        users.withdrawn(
            request.recipients().stream().map(NotificationRequest.Recipient::userId).toList());
    if (!withdrawn.isEmpty()) {
      log.info("탈퇴한 회원은 건너뛰어요 (탈퇴 전에 만든 요청이 늦게 옴): 회원 수={}", withdrawn.size());
    }
    int created = 0;
    for (NotificationRequest.Recipient recipient : request.recipients()) {
      if (withdrawn.contains(recipient.userId())) {
        continue;
      }
      for (NotificationChannel channel : channels) {
        Optional<String> address = channel.address(recipient);
        if (address.isEmpty()) {
          continue; // 이 채널로는 받지 않아요 (api가 주소를 넣지 않음)
        }
        Optional<DigestCadence> cadence =
            request.type().digest() ? channel.digestCadence() : Optional.empty();
        boolean quiet = recipient.quietEnabled();
        boolean inserted =
            deliveries.insert(
                new DeliveryRepository.NewDelivery(
                    UuidV7.next(clock),
                    recipient.userId(),
                    channel.channel(),
                    address.get(),
                    request.type(),
                    recipient.userId() + ":" + request.dedupKey(),
                    request.title(),
                    request.body(),
                    request.linkPath(),
                    recipient.inboxId(),
                    cadence.isPresent(),
                    quiet,
                    cadence
                        .map(c -> schedule.firstDigest(c, quiet))
                        .orElseGet(() -> schedule.firstAttempt(quiet))));
        if (inserted) {
          created++;
        }
      }
    }
    return created;
  }
}
