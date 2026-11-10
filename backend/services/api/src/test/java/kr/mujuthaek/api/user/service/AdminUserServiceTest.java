package kr.mujuthaek.api.user.service;

import static kr.mujuthaek.api.user.domain.AdminPermission.ACTIVITY;
import static kr.mujuthaek.api.user.domain.AdminPermission.ADMIN_APPOINT;
import static kr.mujuthaek.api.user.domain.AdminPermission.CHAT;
import static kr.mujuthaek.api.user.domain.AdminPermission.NOTICE_REVIEW;
import static kr.mujuthaek.api.user.domain.AdminPermission.PERMISSION_GRANT;
import static kr.mujuthaek.api.user.domain.AdminPermission.PERMISSION_REVOKE;
import static kr.mujuthaek.api.user.domain.AdminPermission.REPORTS;
import static kr.mujuthaek.api.user.domain.AdminPermission.USERS_SUSPEND;
import static kr.mujuthaek.api.user.domain.AdminPermission.USERS_VIEW;
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Set;
import java.util.UUID;
import kr.mujuthaek.api.TestDatabase;
import kr.mujuthaek.api.common.exception.CustomException;
import kr.mujuthaek.api.common.exception.ErrorCode;
import kr.mujuthaek.api.user.domain.AdminPermission;
import kr.mujuthaek.api.user.repository.AdminUserRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.simple.JdbcClient;

/**
 * 관리자 회원 관리 규칙: 「권한 부여」가 있어야 주고 빼고, 가진 권한만 주고 빼고, 「권한 부여」와 그 보유자는 최상위만, 나보다 넓은 사람은 해제·정지 못 하고, 최상위는
 * 아무도 못 바꾸고, 긴급 정지·이용 정지·넘기기·기록.
 */
class AdminUserServiceTest {

  private static final Instant NOW = Instant.parse("2026-10-27T03:00:00Z");

  private final JdbcClient jdbc = JdbcClient.create(TestDatabase.dataSource());
  private final Clock clock = Clock.fixed(NOW, ZoneOffset.UTC);
  private final AdminUserService service =
      new AdminUserService(new AdminUserRepository(jdbc), clock);

  private final UUID top = UUID.randomUUID(); // 최상위
  private final UUID granter = UUID.randomUUID(); // 권한 부여 + 회원 보기·이용 정지·관리자 지정
  private final UUID notices = UUID.randomUUID(); // 공고 검수만
  private final UUID reports = UUID.randomUUID(); // 제보·채팅
  private final UUID kim = UUID.randomUUID(); // 일반 회원
  private final UUID lee = UUID.randomUUID(); // 일반 회원

  @BeforeEach
  void users() {
    jdbc.sql("truncate account.users cascade").update();
    user(top, "최상위", "SUPER_ADMIN", "2026-10-01T00:00:00Z");
    user(granter, "회원관리", "ADMIN", "2026-10-02T00:00:00Z");
    user(notices, "공고관리", "ADMIN", "2026-10-03T00:00:00Z");
    user(reports, "신고관리", "ADMIN", "2026-10-04T00:00:00Z");
    user(kim, "김_무주택", "USER", "2026-10-05T00:00:00Z");
    user(lee, "이청년", "USER", "2026-10-06T00:00:00Z");
    give(granter, PERMISSION_GRANT, PERMISSION_REVOKE, USERS_VIEW, USERS_SUSPEND, ADMIN_APPOINT);
    give(notices, NOTICE_REVIEW);
    give(reports, REPORTS, CHAT);
    jdbc.sql(
            "insert into account.social_accounts (id, user_id, provider, provider_user_id)"
                + " values (:id, :u, 'KAKAO', 'k1')")
        .param("id", UUID.randomUUID())
        .param("u", kim)
        .update();
    login(kim);
    login(notices);
  }

  private void user(UUID id, String nickname, String role, String at) {
    jdbc.sql(
            "insert into account.users (id, nickname, role, created_at, updated_at)"
                + " values (:id, :n, :r, cast(:at as timestamptz), now())")
        .param("id", id)
        .param("n", nickname)
        .param("r", role)
        .param("at", at)
        .update();
  }

  private void give(UUID id, AdminPermission... permissions) {
    for (var p : permissions) {
      jdbc.sql("insert into account.admin_permissions (user_id, permission) values (:u, :p)")
          .param("u", id)
          .param("p", p.name())
          .update();
    }
  }

  private void login(UUID id) {
    jdbc.sql(
            "insert into account.refresh_tokens (id, user_id, token_hash, expires_at)"
                + " values (:id, :u, :h, now() + interval '1 day')")
        .param("id", UUID.randomUUID())
        .param("u", id)
        .param("h", "h-" + id)
        .update();
  }

  private long logins(UUID id) {
    return jdbc.sql("select count(*) from account.refresh_tokens where user_id = :u")
        .param("u", id)
        .query(Long.class)
        .single();
  }

  private static void denied(Runnable action, ErrorCode code, String message) {
    assertThatThrownBy(action::run)
        .isInstanceOf(CustomException.class)
        .satisfies(
            e -> {
              assertThat(((CustomException) e).errorCode()).isEqualTo(code);
              assertThat(e.getMessage()).contains(message);
            });
  }

  @Test
  void 닉네임_일부나_ID로_찾고_관리자_정지로_거른다() {
    assertThat(service.search(null, null, 0).total()).isEqualTo(6);
    // 「_」는 아무 글자가 아니라 글자 그대로 찾아요
    assertThat(service.search("_무", null, 0).items())
        .singleElement()
        .satisfies(
            u -> {
              assertThat(u.id()).isEqualTo(kim);
              assertThat(u.providers()).containsExactly("KAKAO");
            });
    assertThat(service.search(lee.toString(), null, 0).items()).hasSize(1);
    assertThat(service.search(null, "ADMIN", 0).items())
        .extracting(u -> u.nickname())
        .containsExactly("신고관리", "공고관리", "회원관리", "최상위");
    assertThat(service.search(null, "ADMIN", 0).items().getLast().permissions()).isEmpty();
    assertThat(service.search(null, "USER", 0).total()).isEqualTo(2);
  }

  @Test
  void 관리자_화면_상태는_DB의_지금_권한이고_최상위는_전부() {
    assertThat(service.access(top).effective()).containsExactlyInAnyOrder(AdminPermission.values());
    assertThat(service.access(notices).has(NOTICE_REVIEW)).isTrue();
    assertThat(service.access(notices).has(REPORTS)).isFalse();
    assertThat(service.access(kim).active()).isFalse();
    assertThat(service.me(granter).permissions())
        .containsExactlyInAnyOrder(
            "PERMISSION_GRANT",
            "PERMISSION_REVOKE",
            "USERS_VIEW",
            "USERS_SUSPEND",
            "ADMIN_APPOINT");
  }

  @Test
  void 권한_부여가_있어야_주고_빼고_가진_권한만() {
    // 공고관리는 「권한 부여」가 없어요
    denied(
        () -> service.setPermissions(reports, Set.of(REPORTS, CHAT, NOTICE_REVIEW), notices),
        ErrorCode.FORBIDDEN,
        "「권한 부여」나 「권한 박탈」 권한이 없어요");
    // 회원관리는 가진 「회원 보기」는 줄 수 있어요 (신고관리의 다른 권한은 그대로)
    var r = service.setPermissions(reports, Set.of(REPORTS, CHAT, USERS_VIEW), granter);
    assertThat(r.permissions()).containsExactlyInAnyOrder("REPORTS", "CHAT", "USERS_VIEW");
    // 가지지 않은 「공고 검수」는 줄 수도, 「채팅 제재」는 뺄 수도 없어요
    denied(
        () ->
            service.setPermissions(
                reports, Set.of(REPORTS, CHAT, USERS_VIEW, NOTICE_REVIEW), granter),
        ErrorCode.FORBIDDEN,
        "공고 검수");
    denied(
        () -> service.setPermissions(reports, Set.of(REPORTS, USERS_VIEW), granter),
        ErrorCode.FORBIDDEN,
        "채팅 제재");
  }

  @Test
  void 권한_부여_자체와_그_보유자는_최상위만() {
    denied(
        () -> service.setPermissions(notices, Set.of(NOTICE_REVIEW, PERMISSION_GRANT), granter),
        ErrorCode.FORBIDDEN,
        "최상위 관리자만 주고 뺄 수 있어요");
    // 최상위가 공고관리에게 「권한 부여」를 주면, 회원관리는 공고관리를 더 못 건드려요
    service.setPermissions(notices, Set.of(NOTICE_REVIEW, PERMISSION_GRANT), top);
    denied(
        () ->
            service.setPermissions(
                notices, Set.of(NOTICE_REVIEW, PERMISSION_GRANT, USERS_VIEW), granter),
        ErrorCode.FORBIDDEN,
        "최상위 관리자만 바꿀 수 있어요");
    // 공고관리도 「권한 부여」를 남에게 줄 수 없어요 (스스로 퍼지지 않게)
    denied(
        () -> service.setPermissions(reports, Set.of(REPORTS, CHAT, PERMISSION_GRANT), notices),
        ErrorCode.FORBIDDEN,
        "최상위 관리자만");
    // 「권한 박탈」도 마찬가지예요
    denied(
        () -> service.setPermissions(reports, Set.of(REPORTS, CHAT, PERMISSION_REVOKE), granter),
        ErrorCode.FORBIDDEN,
        "최상위 관리자만 주고 뺄 수 있어요");
  }

  @Test
  void 부여만_있으면_주기만_박탈만_있으면_빼기만() {
    service.changeRole(kim, "ADMIN", top);
    service.setPermissions(kim, Set.of(NOTICE_REVIEW), top);
    service.changeRole(lee, "ADMIN", top);
    give(notices, PERMISSION_REVOKE); // 공고관리: 공고 검수 + 권한 박탈
    give(reports, PERMISSION_GRANT, NOTICE_REVIEW); // 신고관리: 제보·채팅 + 권한 부여 + 공고 검수

    denied(
        () -> service.setPermissions(lee, Set.of(NOTICE_REVIEW), notices),
        ErrorCode.FORBIDDEN,
        "「권한 부여」가 필요해요");
    assertThat(service.setPermissions(kim, Set.of(), notices).permissions()).isEmpty();

    assertThat(service.setPermissions(lee, Set.of(NOTICE_REVIEW), reports).permissions())
        .containsExactly("NOTICE_REVIEW");
    denied(
        () -> service.setPermissions(lee, Set.of(), reports), ErrorCode.FORBIDDEN, "「권한 박탈」이 필요해요");
  }

  @Test
  void 자기_자신과_최상위는_못_바꾼다() {
    denied(() -> service.setPermissions(granter, Set.of(), granter), ErrorCode.CONFLICT, "내 회원 구분");
    denied(() -> service.changeRole(top, "USER", granter), ErrorCode.FORBIDDEN, "최상위 관리자는");
    denied(() -> service.suspend(top, "사유", null, granter), ErrorCode.FORBIDDEN, "최상위 관리자는");
  }

  @Test
  void 지정은_관리자_지정_권한_해제는_나보다_넓은_사람이면_못_한다() {
    var appointed = service.changeRole(kim, "ADMIN", granter);
    assertThat(appointed.role()).isEqualTo("ADMIN");
    assertThat(appointed.permissions()).isEmpty(); // 지정만 하면 권한은 없어요

    // 공고관리는 회원관리에게 없는 「공고 검수」를 가져서 회원관리가 해제할 수 없어요
    denied(() -> service.changeRole(notices, "USER", granter), ErrorCode.FORBIDDEN, "공고 검수");
    // 최상위는 해제할 수 있고, 권한이 모두 빠지고 로그인이 끊겨요
    var dismissed = service.changeRole(notices, "USER", top);
    assertThat(dismissed.role()).isEqualTo("USER");
    assertThat(dismissed.permissions()).isEmpty();
    assertThat(logins(notices)).isZero();
    // 「관리자 지정」이 없는 관리자는 지정할 수 없어요
    denied(() -> service.changeRole(lee, "ADMIN", reports), ErrorCode.FORBIDDEN, "관리자 지정");
  }

  @Test
  void 이용_정지는_로그인을_끊고_기간이_지나면_풀린다() {
    var s = service.suspend(kim, "도배", NOW.plusSeconds(3600), granter);
    assertThat(s.suspension().reason()).isEqualTo("도배");
    assertThat(logins(kim)).isZero();
    assertThat(service.suspended(kim)).isTrue();
    assertThat(service.search(null, "SUSPENDED", 0).items())
        .extracting(u -> u.id())
        .containsExactly(kim);
    // 정지 중이면 관리자로 지정할 수 없어요
    denied(() -> service.changeRole(kim, "ADMIN", top), ErrorCode.CONFLICT, "이용 정지 중");
    // 한 시간 뒤에는 저절로 풀려요
    var later =
        new AdminUserService(
            new AdminUserRepository(jdbc), Clock.fixed(NOW.plusSeconds(3601), ZoneOffset.UTC));
    assertThat(later.suspended(kim)).isFalse();

    service.unsuspend(kim, granter);
    assertThat(service.suspended(kim)).isFalse();
    // 나보다 넓은 관리자(신고관리)는 정지할 수 없어요
    denied(() -> service.suspend(reports, "사유", null, granter), ErrorCode.FORBIDDEN, "제보 처리");
    // 정지된 관리자는 관리자 화면을 못 써요
    service.suspend(reports, "사유", null, top);
    assertThat(service.access(reports).active()).isFalse();
  }

  @Test
  void 긴급_정지는_최상위만_하고_최상위를_뺀_관리자를_멈춘다() {
    denied(() -> service.freeze("의심", granter), ErrorCode.FORBIDDEN, "최상위 관리자만");
    var me = service.freeze("계정 유출 의심", top);
    assertThat(me.freeze().reason()).isEqualTo("계정 유출 의심");
    assertThat(service.access(notices).has(NOTICE_REVIEW)).isFalse();
    assertThat(service.me(notices).active()).isFalse();
    assertThat(service.access(top).active()).isTrue();
    // 정지 중에는 회원관리가 권한을 바꿀 수도 없어요
    denied(() -> service.changeRole(lee, "ADMIN", granter), ErrorCode.FORBIDDEN, "관리자 지정");

    service.unfreeze(top);
    assertThat(service.access(notices).has(NOTICE_REVIEW)).isTrue();
  }

  @Test
  void 최상위_넘기기는_로그인한_지_10분_안에_일반_관리자에게() {
    denied(() -> service.transfer(notices, top), ErrorCode.FORBIDDEN, "10분");
    jdbc.sql("update account.users set last_login_at = :t where id = :id")
        .param("t", java.sql.Timestamp.from(NOW.minusSeconds(60)))
        .param("id", top)
        .update();
    denied(() -> service.transfer(kim, top), ErrorCode.CONFLICT, "일반 관리자에게만");
    denied(() -> service.transfer(top, granter), ErrorCode.FORBIDDEN, "최상위 관리자만");

    var to = service.transfer(notices, top);
    assertThat(to.role()).isEqualTo("SUPER_ADMIN");
    assertThat(service.access(notices).isSuper()).isTrue();
    // 넘긴 사람은 모든 권한을 가진 일반 관리자
    var was = service.access(top);
    assertThat(was.isSuper()).isFalse();
    assertThat(was.permissions()).containsExactlyInAnyOrder(AdminPermission.values());
  }

  @Test
  void 처음_최상위_지정은_최상위가_없을_때_정한_회원만() {
    // 최상위가 이미 있으면 아무것도 안 해요
    assertThat(service.bootstrapSuper(kim)).isFalse();
    assertThat(service.access(kim).isSuper()).isFalse();

    jdbc.sql("update account.users set role = 'ADMIN' where id = :id").param("id", top).update();
    // 없는 회원·이용 정지 중인 회원은 지정하지 않아요
    assertThat(service.bootstrapSuper(UUID.randomUUID())).isFalse();
    service.suspend(lee, "도배", null, granter);
    assertThat(service.bootstrapSuper(lee)).isFalse();

    // 일반 관리자였어도 받은 권한 줄은 지우고 최상위로 (최상위는 전부 가진 것으로 봐요)
    assertThat(service.bootstrapSuper(notices)).isTrue();
    assertThat(service.access(notices).isSuper()).isTrue();
    assertThat(
            jdbc.sql("select count(*) from account.admin_permissions where user_id = :u")
                .param("u", notices)
                .query(Long.class)
                .single())
        .isZero();
    assertThat(service.changes(30))
        .first()
        .satisfies(
            c -> {
              assertThat(c.kind()).isEqualTo("APPOINT");
              assertThat(c.userId()).isEqualTo(notices);
              assertThat(c.changedBy()).isNull();
            });
    // 한 번 정해지면 값을 그대로 둬도 다시 바뀌지 않아요
    assertThat(service.bootstrapSuper(kim)).isFalse();
  }

  @Test
  void 모든_변경을_최근_순으로_기록한다() {
    service.changeRole(kim, "ADMIN", granter);
    service.setPermissions(kim, Set.of(USERS_VIEW), granter);
    service.suspend(lee, "도배", null, granter);
    service.freeze(null, top);

    assertThat(service.changes(30))
        .extracting(
            c ->
                c.kind()
                    + ":"
                    + c.permission()
                    + ":"
                    + c.nickname()
                    + " by "
                    + c.changedByNickname())
        .containsExactly(
            "FREEZE:null:null by 최상위",
            "SUSPEND:null:이청년 by 회원관리",
            "GRANT:USERS_VIEW:김_무주택 by 회원관리",
            "APPOINT:null:김_무주택 by 회원관리");
    assertThat(service.names(java.util.List.of(granter, UUID.randomUUID())))
        .extracting(n -> n.nickname())
        .containsExactly("회원관리");
    assertThat(service.access(kim).permissions()).containsExactly(USERS_VIEW);
    assertThat(service.access(lee).suspended()).isTrue();
    // 처리 기록 보기 권한만으로는 회원을 바꿀 수 없어요
    give(reports, ACTIVITY);
    denied(() -> service.changeRole(lee, "ADMIN", reports), ErrorCode.FORBIDDEN, "관리자 지정");
  }
}
