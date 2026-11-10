package kr.mujuthaek.api.user.service;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Collections;
import java.util.EnumSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.stream.Collectors;
import kr.mujuthaek.api.common.exception.CustomException;
import kr.mujuthaek.api.common.exception.ErrorCode;
import kr.mujuthaek.api.user.domain.AdminPermission;
import kr.mujuthaek.api.user.domain.Role;
import kr.mujuthaek.api.user.dto.response.AdminMeResponse;
import kr.mujuthaek.api.user.dto.response.AdminUserResponse;
import kr.mujuthaek.api.user.repository.AdminUserRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 관리자 회원 관리: 회원 찾기, 관리자 지정·해제, 권한 주고 빼기, 이용 정지, 최상위 넘기기, 긴급 정지, 변경 기록.
 *
 * <p>규칙 (최상위는 모든 권한을 가진 것으로 봐요):
 *
 * <ol>
 *   <li>자기 자신의 단계·권한·정지는 바꿀 수 없어요
 *   <li>권한 주기는 「권한 부여」, 빼기는 「권한 박탈」이 있어야 해요. 하나만 가졌으면 그것만 할 수 있고, 내가 가진 권한만 주고 뺄 수 있어요
 *   <li>「권한 부여」·「권한 박탈」 자체를 주고 빼는 일, 그 권한을 가진 관리자를 해제·정지하거나 권한을 바꾸는 일은 최상위만 해요 (권한을 다루는 권한이 스스로 퍼지지
 *       않게)
 *   <li>관리자를 해제·정지하면 그 사람의 권한이 모두 멈추니, 그 사람의 권한을 내가 모두 가지고 있어야 해요 (나보다 넓은 사람은 못 건드림)
 *   <li>최상위는 아무도 바꿀 수 없어요. 최상위가 직접 넘기기만 해요 (로그인한 지 10분 안에)
 *   <li>모든 변경은 기록하고, 해제·정지하면 그 회원의 로그인을 바로 끊어요. 관리자 화면 권한은 요청마다 DB로 확인해서 바로 반영돼요
 * </ol>
 */
@Service
public class AdminUserService {

  private static final Logger log = LoggerFactory.getLogger(AdminUserService.class);
  private static final int PAGE_SIZE = 30;
  private static final Duration TRANSFER_LOGIN_WINDOW = Duration.ofMinutes(10);

  /** 오류 문구에 쓰는 권한 이름 (화면 이름과 같아요) */
  static final Map<AdminPermission, String> LABELS =
      Map.ofEntries(
          Map.entry(AdminPermission.NOTICE_REVIEW, "공고 검수"),
          Map.entry(AdminPermission.BENEFIT_REVIEW, "혜택 검수"),
          Map.entry(AdminPermission.SOURCES, "수집 출처"),
          Map.entry(AdminPermission.CRITERIA, "판정 기준"),
          Map.entry(AdminPermission.REPORTS, "제보 처리"),
          Map.entry(AdminPermission.CHAT, "채팅 제재"),
          Map.entry(AdminPermission.USERS_VIEW, "회원 보기"),
          Map.entry(AdminPermission.USERS_SUSPEND, "이용 정지"),
          Map.entry(AdminPermission.ADMIN_APPOINT, "관리자 지정"),
          Map.entry(AdminPermission.PERMISSION_GRANT, "권한 부여"),
          Map.entry(AdminPermission.PERMISSION_REVOKE, "권한 박탈"),
          Map.entry(AdminPermission.TRAFFIC, "트래픽 보기"),
          Map.entry(AdminPermission.ACTIVITY, "처리 기록 보기"));

  /** 권한을 다루는 권한: 이 둘을 주고 빼는 일과 이 둘을 가진 관리자를 바꾸는 일은 최상위만 */
  private static final Set<AdminPermission> MANAGING =
      EnumSet.of(AdminPermission.PERMISSION_GRANT, AdminPermission.PERMISSION_REVOKE);

  private final AdminUserRepository users;
  private final Clock clock;

  public AdminUserService(AdminUserRepository users, Clock clock) {
    this.users = users;
    this.clock = clock;
  }

  // ---------- 상태 ----------

  /** 관리자 화면 요청마다 쓰는 지금 상태. 없는 회원이면 일반 회원처럼 아무 권한 없음. */
  @Transactional(readOnly = true)
  public AdminAccess access(UUID userId) {
    return users
        .access(userId, clock.instant())
        .map(
            a ->
                new AdminAccess(
                    userId,
                    Role.valueOf(a.role()),
                    a.permissions().stream()
                        .map(AdminPermission::valueOf)
                        .collect(
                            Collectors.toCollection(() -> EnumSet.noneOf(AdminPermission.class))),
                    a.suspended(),
                    a.frozen()))
        .orElse(new AdminAccess(userId, Role.USER, Set.of(), false, false));
  }

  /** 지금 이용 정지 중인지 (로그인·재발급·쓰기 요청을 막을 때). */
  @Transactional(readOnly = true)
  public boolean suspended(UUID userId) {
    return users.suspended(userId, clock.instant());
  }

  /** 관리자 화면의 내 권한. */
  @Transactional(readOnly = true)
  public AdminMeResponse me(UUID userId) {
    AdminAccess me = access(userId);
    var row = users.find(userId, clock.instant()).orElseThrow(() -> forbidden("관리자가 아니에요"));
    var freeze = users.freezeState().orElse(null);
    return new AdminMeResponse(
        userId,
        row.nickname(),
        me.role().name(),
        me.active() ? me.effective().stream().map(Enum::name).toList() : List.of(),
        me.active(),
        freeze == null ? null : new AdminMeResponse.Freeze(freeze.reason(), freeze.frozenAt()));
  }

  // ---------- 찾기 ----------

  /** 회원 찾기 (한 쪽 30명). filter: USER·ADMIN·SUSPENDED */
  @Transactional(readOnly = true)
  public AdminUserResponse.Page search(String query, String filter, int page) {
    String q = query == null || query.isBlank() ? null : query.strip();
    String f = filter == null || filter.isBlank() ? null : filter;
    int p = Math.max(0, page);
    Instant now = clock.instant();
    return new AdminUserResponse.Page(
        users.search(q, f, now, PAGE_SIZE, p * PAGE_SIZE).stream()
            .map(AdminUserService::response)
            .toList(),
        users.count(q, f, now));
  }

  /** 이름만 (처리 기록에서 관리자 이름 찾기). 최대 100명. */
  @Transactional(readOnly = true)
  public List<AdminUserResponse.Name> names(List<UUID> ids) {
    return users.findAll(ids.stream().distinct().limit(100).toList(), clock.instant()).stream()
        .map(r -> new AdminUserResponse.Name(r.id(), r.nickname(), r.role()))
        .toList();
  }

  // ---------- 관리자 지정·해제 ----------

  /** 관리자 지정(ADMIN)·해제(USER). 「관리자 지정」 권한. */
  @Transactional
  public AdminUserResponse changeRole(UUID userId, String role, UUID actorId) {
    AdminAccess actor = require(actorId, AdminPermission.ADMIN_APPOINT);
    notSelf(userId, actorId);
    String current =
        users.lockRole(userId).orElseThrow(() -> new CustomException(ErrorCode.NOT_FOUND));
    notSuper(current);
    Instant now = clock.instant();
    if (role.equals(current)) {
      return find(userId);
    }
    if ("ADMIN".equals(role)) {
      if (users.suspended(userId, now)) {
        throw conflict("이용 정지 중인 회원은 관리자로 지정할 수 없어요");
      }
      users.setRole(userId, "ADMIN", now);
      users.record(userId, "APPOINT", null, null, actorId, now);
    } else {
      Set<AdminPermission> had = permissionsOf(userId);
      canTouchWhole(actor, had, "해제");
      users.revokeAll(userId);
      users.setRole(userId, "USER", now);
      users.revokeLogins(userId);
      users.record(userId, "DISMISS", null, labels(had), actorId, now);
    }
    log.info("관리자 단계 변경: user={} role={} by={}", userId, role, actorId);
    return find(userId);
  }

  // ---------- 권한 주고 빼기 ----------

  /** 일반 관리자의 권한을 wanted로 맞춰요. 주기는 「권한 부여」, 빼기는 「권한 박탈」, 내가 가진 권한만. */
  @Transactional
  public AdminUserResponse setPermissions(UUID userId, Set<AdminPermission> wanted, UUID actorId) {
    AdminAccess actor = access(actorId);
    if (!actor.has(AdminPermission.PERMISSION_GRANT)
        && !actor.has(AdminPermission.PERMISSION_REVOKE)) {
      throw forbidden("「권한 부여」나 「권한 박탈」 권한이 없어요");
    }
    notSelf(userId, actorId);
    String current =
        users.lockRole(userId).orElseThrow(() -> new CustomException(ErrorCode.NOT_FOUND));
    notSuper(current);
    if (!"ADMIN".equals(current)) {
      throw conflict("일반 회원이에요. 먼저 관리자로 지정해 주세요");
    }
    Set<AdminPermission> had = permissionsOf(userId);
    Set<AdminPermission> add = EnumSet.noneOf(AdminPermission.class);
    add.addAll(wanted);
    add.removeAll(had);
    Set<AdminPermission> remove = EnumSet.noneOf(AdminPermission.class);
    remove.addAll(had);
    remove.removeAll(wanted);
    if (add.isEmpty() && remove.isEmpty()) {
      return find(userId);
    }
    if (!add.isEmpty() && !actor.has(AdminPermission.PERMISSION_GRANT)) {
      throw forbidden("권한을 주려면 「권한 부여」가 필요해요: " + labels(add));
    }
    if (!remove.isEmpty() && !actor.has(AdminPermission.PERMISSION_REVOKE)) {
      throw forbidden("권한을 빼려면 「권한 박탈」이 필요해요: " + labels(remove));
    }
    if (!actor.isSuper()) {
      if (!Collections.disjoint(had, MANAGING)) {
        throw forbidden("「권한 부여」·「권한 박탈」을 가진 관리자의 권한은 최상위 관리자만 바꿀 수 있어요");
      }
      if (!Collections.disjoint(add, MANAGING) || !Collections.disjoint(remove, MANAGING)) {
        throw forbidden("「권한 부여」·「권한 박탈」은 최상위 관리자만 주고 뺄 수 있어요");
      }
      Set<AdminPermission> touched = EnumSet.noneOf(AdminPermission.class);
      touched.addAll(add);
      touched.addAll(remove);
      touched.removeAll(actor.effective());
      if (!touched.isEmpty()) {
        throw forbidden("내가 가지지 않은 권한은 주거나 뺄 수 없어요: " + labels(touched));
      }
    }
    Instant now = clock.instant();
    for (AdminPermission p : add) {
      users.grant(userId, p.name(), actorId, now);
      users.record(userId, "GRANT", p.name(), null, actorId, now);
    }
    for (AdminPermission p : remove) {
      users.revoke(userId, p.name());
      users.record(userId, "REVOKE", p.name(), null, actorId, now);
    }
    log.info("관리자 권한 변경: user={} add={} remove={} by={}", userId, add, remove, actorId);
    return find(userId);
  }

  // ---------- 이용 정지 ----------

  /** 이용 정지 (이미 정지 중이면 이유·기간을 바꿔요). 「이용 정지」 권한. */
  @Transactional
  public AdminUserResponse suspend(UUID userId, String reason, Instant until, UUID actorId) {
    AdminAccess actor = require(actorId, AdminPermission.USERS_SUSPEND);
    notSelf(userId, actorId);
    String current =
        users.lockRole(userId).orElseThrow(() -> new CustomException(ErrorCode.NOT_FOUND));
    notSuper(current);
    Instant now = clock.instant();
    if (until != null && !until.isAfter(now)) {
      throw new CustomException(ErrorCode.VALIDATION_FAILED, "정지 기간은 지금보다 뒤여야 해요");
    }
    if ("ADMIN".equals(current)) {
      canTouchWhole(actor, permissionsOf(userId), "정지");
    }
    users.suspend(userId, reason.strip(), until, actorId, now);
    users.revokeLogins(userId);
    users.record(userId, "SUSPEND", null, reason.strip(), actorId, now);
    log.info("이용 정지: user={} until={} by={}", userId, until, actorId);
    return find(userId);
  }

  /** 이용 정지 해제. 「이용 정지」 권한. */
  @Transactional
  public AdminUserResponse unsuspend(UUID userId, UUID actorId) {
    AdminAccess actor = require(actorId, AdminPermission.USERS_SUSPEND);
    notSelf(userId, actorId);
    String current =
        users.lockRole(userId).orElseThrow(() -> new CustomException(ErrorCode.NOT_FOUND));
    if ("ADMIN".equals(current)) {
      canTouchWhole(actor, permissionsOf(userId), "정지 해제");
    }
    Instant now = clock.instant();
    if (users.unsuspend(userId) > 0) {
      users.record(userId, "UNSUSPEND", null, null, actorId, now);
      log.info("이용 정지 해제: user={} by={}", userId, actorId);
    }
    return find(userId);
  }

  // ---------- 최상위 고유 ----------

  /**
   * 최상위 관리자 넘기기. 받는 사람은 일반 관리자여야 하고, 넘긴 사람은 모든 권한을 가진 일반 관리자가 돼요 (새 최상위가 나중에 조정). 로그인한 지 10분 안에만.
   */
  @Transactional
  public AdminUserResponse transfer(UUID userId, UUID actorId) {
    requireSuper(actorId);
    notSelf(userId, actorId);
    Instant now = clock.instant();
    var me = users.find(actorId, now).orElseThrow();
    if (me.lastLoginAt() == null
        || me.lastLoginAt().toInstant().isBefore(now.minus(TRANSFER_LOGIN_WINDOW))) {
      throw forbidden("최상위 관리자는 로그인한 지 10분 안에만 넘길 수 있어요. 다시 로그인해 주세요");
    }
    users.lockRole(actorId);
    String current =
        users.lockRole(userId).orElseThrow(() -> new CustomException(ErrorCode.NOT_FOUND));
    if (!"ADMIN".equals(current)) {
      throw conflict("일반 관리자에게만 넘길 수 있어요. 먼저 관리자로 지정해 주세요");
    }
    if (users.suspended(userId, now)) {
      throw conflict("이용 정지 중인 관리자에게는 넘길 수 없어요");
    }
    users.setRole(actorId, "ADMIN", now); // 최상위는 한 명뿐이라 먼저 내려요
    for (AdminPermission p : AdminPermission.values()) {
      users.grant(actorId, p.name(), actorId, now);
    }
    users.revokeAll(userId);
    users.setRole(userId, "SUPER_ADMIN", now);
    users.record(userId, "TRANSFER", null, null, actorId, now);
    log.info("최상위 관리자 넘기기: to={} from={}", userId, actorId);
    return find(userId);
  }

  /**
   * 처음 최상위 지정 (서버가 뜰 때 ADMIN_BOOTSTRAP_USER_ID로). 최상위가 이미 있으면 아무것도 안 해요. 그 뒤로 바꾸는 건 화면의 넘기기로만.
   *
   * @return 이번에 지정했으면 true
   */
  @Transactional
  public boolean bootstrapSuper(UUID userId) {
    if (users.hasSuper()) {
      log.info("최상위 관리자가 이미 있어 처음 지정을 건너뛰어요: user={}", userId);
      return false;
    }
    if (users.lockRole(userId).isEmpty()) {
      log.warn("처음 최상위로 지정할 회원이 없어요. 먼저 가입한 뒤 그 회원 ID를 넣어 주세요: user={}", userId);
      return false;
    }
    Instant now = clock.instant();
    if (users.suspended(userId, now)) {
      log.warn("이용 정지 중인 회원은 처음 최상위로 지정하지 않아요: user={}", userId);
      return false;
    }
    users.revokeAll(userId); // 최상위는 권한 줄 없이 전부 가진 것으로 봐요
    users.setRole(userId, "SUPER_ADMIN", now);
    users.record(userId, "APPOINT", null, "환경 변수로 처음 최상위 지정", null, now);
    log.info("처음 최상위 관리자 지정: user={}", userId);
    return true;
  }

  /** 관리자 긴급 정지: 최상위를 뺀 모든 관리자의 관리자 화면을 멈춰요. 이미 정지 중이면 그대로. */
  @Transactional
  public AdminMeResponse freeze(String reason, UUID actorId) {
    requireSuper(actorId);
    Instant now = clock.instant();
    String note = reason == null || reason.isBlank() ? null : reason.strip();
    if (users.freeze(note, actorId, now) > 0) {
      users.record(null, "FREEZE", null, note, actorId, now);
      log.warn("관리자 긴급 정지: by={}", actorId);
    }
    return me(actorId);
  }

  @Transactional
  public AdminMeResponse unfreeze(UUID actorId) {
    requireSuper(actorId);
    Instant now = clock.instant();
    if (users.unfreeze() > 0) {
      users.record(null, "UNFREEZE", null, null, actorId, now);
      log.warn("관리자 긴급 정지 풀기: by={}", actorId);
    }
    return me(actorId);
  }

  // ---------- 기록 ----------

  /** 최근 days일 변경 기록 (최대 300줄). */
  @Transactional(readOnly = true)
  public List<AdminUserResponse.Change> changes(int days) {
    Instant since = clock.instant().minus(Duration.ofDays(Math.clamp(days, 1, 90)));
    return users.changes(since, 300).stream()
        .map(
            c ->
                new AdminUserResponse.Change(
                    c.id(),
                    c.changedAt(),
                    c.kind(),
                    c.permission(),
                    c.note(),
                    c.userId(),
                    c.nickname(),
                    c.changedBy(),
                    c.changedByNickname()))
        .toList();
  }

  // ---------- 규칙 ----------

  /** 서비스에서도 다시 확인해요 (보안 설정의 경로 검사와 겹쳐도, 다른 곳에서 불러도 안전하게). */
  private AdminAccess require(UUID actorId, AdminPermission permission) {
    AdminAccess actor = access(actorId);
    if (!actor.has(permission)) {
      throw forbidden("「" + LABELS.get(permission) + "」 권한이 없어요");
    }
    return actor;
  }

  private void requireSuper(UUID actorId) {
    AdminAccess actor = access(actorId);
    if (!actor.isSuper() || !actor.active()) {
      throw forbidden("최상위 관리자만 할 수 있어요");
    }
  }

  /** 해제·정지처럼 그 사람의 권한을 모두 멈추는 일: 그 권한을 내가 모두 가져야 하고, 「권한 부여」·「권한 박탈」을 가진 사람은 최상위만. */
  private static void canTouchWhole(AdminAccess actor, Set<AdminPermission> had, String what) {
    if (actor.isSuper()) {
      return;
    }
    if (!Collections.disjoint(had, MANAGING)) {
      throw forbidden("「권한 부여」·「권한 박탈」을 가진 관리자는 최상위 관리자만 " + what + "할 수 있어요");
    }
    Set<AdminPermission> missing = EnumSet.noneOf(AdminPermission.class);
    missing.addAll(had);
    missing.removeAll(actor.effective());
    if (!missing.isEmpty()) {
      throw forbidden("내가 가지지 않은 권한(" + labels(missing) + ")을 가진 관리자라 " + what + "할 수 없어요");
    }
  }

  private static void notSelf(UUID userId, UUID actorId) {
    if (userId.equals(actorId)) {
      throw conflict("내 회원 구분·권한·정지는 바꿀 수 없어요. 다른 관리자에게 부탁해 주세요");
    }
  }

  private static void notSuper(String role) {
    if ("SUPER_ADMIN".equals(role)) {
      throw forbidden("최상위 관리자는 바꿀 수 없어요");
    }
  }

  private Set<AdminPermission> permissionsOf(UUID userId) {
    Set<AdminPermission> set = EnumSet.noneOf(AdminPermission.class);
    users.permissions(userId).forEach(p -> set.add(AdminPermission.valueOf(p)));
    return set;
  }

  private AdminUserResponse find(UUID userId) {
    return response(users.find(userId, clock.instant()).orElseThrow());
  }

  static String labels(Set<AdminPermission> permissions) {
    return permissions.isEmpty()
        ? null
        : permissions.stream().sorted().map(LABELS::get).collect(Collectors.joining(", "));
  }

  private static CustomException forbidden(String detail) {
    return new CustomException(ErrorCode.FORBIDDEN, detail);
  }

  private static CustomException conflict(String detail) {
    return new CustomException(ErrorCode.CONFLICT, detail);
  }

  private static AdminUserResponse response(AdminUserRepository.Row r) {
    var s = r.suspension();
    return new AdminUserResponse(
        r.id(),
        r.nickname(),
        r.role(),
        r.providers(),
        r.joinedAt(),
        r.lastLoginAt(),
        List.copyOf(r.permissions()),
        s == null ? null : new AdminUserResponse.Suspension(s.reason(), s.until(), s.at()));
  }
}
