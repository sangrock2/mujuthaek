package kr.mujuthaek.api.notice.service.internal;

import java.time.Clock;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import kr.mujuthaek.api.common.event.PolicyHidden;
import kr.mujuthaek.api.common.exception.CustomException;
import kr.mujuthaek.api.common.exception.ErrorCode;
import kr.mujuthaek.api.notice.dto.response.AdminPolicyDuplicateResponse;
import kr.mujuthaek.api.notice.repository.PolicyDuplicateRepository;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 정책 사업 중복 의심 (2026-10-28 사용자 결정 A안). 정책을 처음 받을 때 같은 사업이 먼저 있으면 후보로 올리고, 관리자가 「둘 다 둠」 또는 「나중 것 숨김」을
 * 골라요. 자동으로 지우지 않아요 (출처에 두 번 올라온 사업은 내용이 조금씩 달라요).
 */
@Service
public class PolicyDuplicateService {

  private static final Set<String> STATUSES = Set.of("PENDING", "KEPT_BOTH", "HIDDEN");

  /** 관리자가 고르는 처리 → 후보 상태 */
  private static final Map<String, String> ACTIONS =
      Map.of("KEEP_BOTH", "KEPT_BOTH", "HIDE_LATER", "HIDDEN");

  private final PolicyDuplicateRepository duplicates;
  private final Clock clock;
  private final ApplicationEventPublisher events;

  public PolicyDuplicateService(
      PolicyDuplicateRepository duplicates, Clock clock, ApplicationEventPublisher events) {
    this.duplicates = duplicates;
    this.clock = clock;
    this.events = events;
  }

  /** 새로 받은 사업을 먼저 있던 사업과 견줘 같아 보이면 후보로 올려요. 정책을 처음 저장한 같은 트랜잭션에서 불려요. */
  public int flag(UUID rawPolicyId) {
    return duplicates.flag(rawPolicyId, clock.instant());
  }

  public AdminPolicyDuplicateResponse list(String status) {
    String s = status == null || status.isBlank() ? "PENDING" : status;
    if (!STATUSES.contains(s)) {
      throw new CustomException(
          ErrorCode.VALIDATION_FAILED, "status: PENDING · KEPT_BOTH · HIDDEN 중 하나예요");
    }
    List<PolicyDuplicateRepository.CandidateRow> rows = duplicates.list(s);
    Map<String, Integer> counts = duplicates.counts();
    return new AdminPolicyDuplicateResponse(
        rows.stream().map(AdminPolicyDuplicateResponse.Item::of).toList(),
        new AdminPolicyDuplicateResponse.Counts(
            counts.getOrDefault("PENDING", 0),
            counts.getOrDefault("KEPT_BOTH", 0),
            counts.getOrDefault("HIDDEN", 0)));
  }

  public AdminPolicyDuplicateResponse.Counts counts() {
    Map<String, Integer> counts = duplicates.counts();
    return new AdminPolicyDuplicateResponse.Counts(
        counts.getOrDefault("PENDING", 0),
        counts.getOrDefault("KEPT_BOTH", 0),
        counts.getOrDefault("HIDDEN", 0));
  }

  /** 「둘 다 둠」(KEEP_BOTH) 또는 「나중 것 숨김」(HIDE_LATER). 이미 처리했거나 없는 후보면 409. */
  @Transactional
  public void decide(UUID later, UUID earlier, String action, String admin) {
    String status = ACTIONS.get(action);
    if (status == null) {
      throw new CustomException(
          ErrorCode.VALIDATION_FAILED, "action: KEEP_BOTH · HIDE_LATER 중 하나예요");
    }
    if (!duplicates.decide(later, earlier, status, admin, clock.instant())) {
      throw new CustomException(ErrorCode.CONFLICT, "이미 처리했거나 없는 중복 후보예요");
    }
    if ("HIDDEN".equals(status)) {
      // 숨긴 사업에 둔 관심은 user가 남은 사업으로 옮겨요(같은 트랜잭션)
      events.publishEvent(new PolicyHidden(later, earlier));
    }
  }
}
