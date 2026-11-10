package kr.mujuthaek.api.user.repository;

import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Timestamp;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.util.Arrays;
import java.util.List;
import java.util.Optional;
import java.util.Set;
import java.util.TreeSet;
import java.util.UUID;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

/** 관리자 회원 관리: 찾기, 관리자 단계·권한, 이용 정지, 긴급 정지, 변경 기록 (account 스키마). */
@Repository
public class AdminUserRepository {

  private static final String COLUMNS =
      "u.id, u.nickname, u.role, u.created_at, u.last_login_at,"
          + " coalesce((select string_agg(s.provider, ',' order by s.provider)"
          + " from account.social_accounts s where s.user_id = u.id), '') as providers,"
          + " coalesce((select string_agg(p.permission, ',' order by p.permission)"
          + " from account.admin_permissions p where p.user_id = u.id), '') as permissions,"
          + " x.reason as suspended_reason, x.until as suspended_until,"
          + " x.suspended_at as suspended_at";

  private static final String FROM =
      " from account.users u left join account.suspensions x on x.user_id = u.id"
          + " and (x.until is null or x.until > :now)";

  /**
   * 회원 한 명.
   *
   * @param providers 이어진 소셜 로그인(KAKAO·NAVER·GOOGLE)
   * @param permissions 받은 관리 권한 (일반 관리자만 줄이 있어요)
   * @param suspension 지금 이용 정지 중이면 그 내용
   */
  public record Row(
      UUID id,
      String nickname,
      String role,
      OffsetDateTime joinedAt,
      OffsetDateTime lastLoginAt,
      List<String> providers,
      Set<String> permissions,
      Suspension suspension) {}

  /**
   * @param until 비어 있으면 해제할 때까지
   */
  public record Suspension(String reason, OffsetDateTime until, OffsetDateTime at) {}

  /** 관리자 화면을 쓸 때 확인하는 지금 상태. */
  public record Access(String role, Set<String> permissions, boolean suspended, boolean frozen) {}

  public record Freeze(String reason, UUID frozenBy, OffsetDateTime frozenAt) {}

  public record Change(
      long id,
      Instant changedAt,
      UUID userId,
      String nickname,
      String kind,
      String permission,
      String note,
      UUID changedBy,
      String changedByNickname) {}

  private final JdbcClient jdbc;

  public AdminUserRepository(JdbcClient jdbc) {
    this.jdbc = jdbc;
  }

  private static Set<String> split(String joined) {
    return joined == null || joined.isEmpty()
        ? Set.of()
        : new TreeSet<>(Arrays.asList(joined.split(",")));
  }

  private static Row row(ResultSet rs) throws SQLException {
    String providers = rs.getString("providers");
    String reason = rs.getString("suspended_reason");
    return new Row(
        rs.getObject("id", UUID.class),
        rs.getString("nickname"),
        rs.getString("role"),
        rs.getObject("created_at", OffsetDateTime.class),
        rs.getObject("last_login_at", OffsetDateTime.class),
        providers.isEmpty() ? List.of() : Arrays.asList(providers.split(",")),
        split(rs.getString("permissions")),
        reason == null
            ? null
            : new Suspension(
                reason,
                rs.getObject("suspended_until", OffsetDateTime.class),
                rs.getObject("suspended_at", OffsetDateTime.class)));
  }

  /**
   * 회원 찾기. query는 닉네임 일부 또는 회원 ID 전체. filter는 USER(일반 회원)·ADMIN(일반·최상위 관리자)·SUSPENDED(지금 이용 정지 중),
   * 없으면 전체. 가입한 지 최근 순.
   *
   * @param offset 건너뛸 수 (페이지)
   */
  public List<Row> search(String query, String filter, Instant now, int limit, int offset) {
    return jdbc.sql(
            "select "
                + COLUMNS
                + FROM
                + " where "
                + where(filter)
                + " order by u.created_at desc, u.id limit :limit offset :offset")
        .param("q", query)
        .param("like", query == null ? null : "%" + escape(query) + "%")
        .param("now", Timestamp.from(now))
        .param("limit", limit)
        .param("offset", offset)
        .query((rs, n) -> row(rs))
        .list();
  }

  public long count(String query, String filter, Instant now) {
    return jdbc.sql("select count(*)" + FROM + " where " + where(filter))
        .param("q", query)
        .param("like", query == null ? null : "%" + escape(query) + "%")
        .param("now", Timestamp.from(now))
        .query(Long.class)
        .single();
  }

  private static String where(String filter) {
    String found =
        "(cast(:q as text) is null or u.nickname ilike :like escape '\\' or u.id::text = :q)";
    return found
        + switch (filter == null ? "" : filter) {
          case "USER" -> " and u.role = 'USER'";
          case "ADMIN" -> " and u.role in ('ADMIN', 'SUPER_ADMIN')";
          case "SUSPENDED" -> " and x.user_id is not null";
          default -> "";
        };
  }

  private static String escape(String s) {
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_");
  }

  /** 여러 회원 (처리 기록의 관리자 이름 찾기 등). 없는 ID는 빠져요. */
  public List<Row> findAll(List<UUID> ids, Instant now) {
    if (ids.isEmpty()) {
      return List.of();
    }
    return jdbc.sql("select " + COLUMNS + FROM + " where u.id in (:ids)")
        .param("ids", ids)
        .param("now", Timestamp.from(now))
        .query((rs, n) -> row(rs))
        .list();
  }

  public Optional<Row> find(UUID id, Instant now) {
    return findAll(List.of(id), now).stream().findFirst();
  }

  /** 관리자 화면 요청마다: 단계·권한·이용 정지·긴급 정지. 없는 회원이면 빈 값. */
  public Optional<Access> access(UUID userId, Instant now) {
    return jdbc.sql(
            "select u.role,"
                + " coalesce((select string_agg(p.permission, ',') from account.admin_permissions p"
                + " where p.user_id = u.id), '') as permissions,"
                + " exists (select 1 from account.suspensions x where x.user_id = u.id"
                + " and (x.until is null or x.until > :now)) as suspended,"
                + " exists (select 1 from account.admin_freeze) as frozen"
                + " from account.users u where u.id = :id")
        .param("id", userId)
        .param("now", Timestamp.from(now))
        .query(
            (rs, n) ->
                new Access(
                    rs.getString("role"),
                    split(rs.getString("permissions")),
                    rs.getBoolean("suspended"),
                    rs.getBoolean("frozen")))
        .optional();
  }

  /** 지금 이용 정지 중인지 (기간이 지난 정지는 아니에요). */
  public boolean suspended(UUID userId, Instant now) {
    return jdbc.sql(
            "select exists (select 1 from account.suspensions where user_id = :id"
                + " and (until is null or until > :now))")
        .param("id", userId)
        .param("now", Timestamp.from(now))
        .query(Boolean.class)
        .single();
  }

  /** 최상위 관리자가 이미 있는지 (한 명뿐이에요). */
  public boolean hasSuper() {
    return jdbc.sql("select exists (select 1 from account.users where role = 'SUPER_ADMIN')")
        .query(Boolean.class)
        .single();
  }

  /** 단계를 읽으면서 그 회원 줄을 잠가요 (같은 회원을 동시에 바꾸지 않게). */
  public Optional<String> lockRole(UUID userId) {
    return jdbc.sql("select role from account.users where id = :id for update")
        .param("id", userId)
        .query(String.class)
        .optional();
  }

  public void setRole(UUID userId, String role, Instant now) {
    jdbc.sql("update account.users set role = :role, updated_at = :now where id = :id")
        .param("role", role)
        .param("now", Timestamp.from(now))
        .param("id", userId)
        .update();
  }

  public Set<String> permissions(UUID userId) {
    return new TreeSet<>(
        jdbc.sql("select permission from account.admin_permissions where user_id = :id")
            .param("id", userId)
            .query(String.class)
            .list());
  }

  public void grant(UUID userId, String permission, UUID by, Instant now) {
    jdbc.sql(
            "insert into account.admin_permissions (user_id, permission, granted_by, granted_at)"
                + " values (:id, :p, :by, :now) on conflict do nothing")
        .param("id", userId)
        .param("p", permission)
        .param("by", by)
        .param("now", Timestamp.from(now))
        .update();
  }

  public void revoke(UUID userId, String permission) {
    jdbc.sql("delete from account.admin_permissions where user_id = :id and permission = :p")
        .param("id", userId)
        .param("p", permission)
        .update();
  }

  public void revokeAll(UUID userId) {
    jdbc.sql("delete from account.admin_permissions where user_id = :id")
        .param("id", userId)
        .update();
  }

  /** 이용 정지 (이미 정지 중이면 이유·기간을 새 값으로). */
  public void suspend(UUID userId, String reason, Instant until, UUID by, Instant now) {
    jdbc.sql(
            "insert into account.suspensions (user_id, reason, until, suspended_by, suspended_at)"
                + " values (:id, :reason, :until, :by, :now) on conflict (user_id) do update set"
                + " reason = excluded.reason, until = excluded.until,"
                + " suspended_by = excluded.suspended_by, suspended_at = excluded.suspended_at")
        .param("id", userId)
        .param("reason", reason)
        .param("until", until == null ? null : Timestamp.from(until))
        .param("by", by)
        .param("now", Timestamp.from(now))
        .update();
  }

  /** 이용 정지 해제. 정지 중이 아니었으면 0. */
  public int unsuspend(UUID userId) {
    return jdbc.sql("delete from account.suspensions where user_id = :id")
        .param("id", userId)
        .update();
  }

  /** 관리자 긴급 정지. 이미 정지 중이면 0. */
  public int freeze(String reason, UUID by, Instant now) {
    return jdbc.sql(
            "insert into account.admin_freeze (reason, frozen_by, frozen_at)"
                + " values (:reason, :by, :now) on conflict do nothing")
        .param("reason", reason)
        .param("by", by)
        .param("now", Timestamp.from(now))
        .update();
  }

  public int unfreeze() {
    return jdbc.sql("delete from account.admin_freeze").update();
  }

  public Optional<Freeze> freezeState() {
    return jdbc.sql("select reason, frozen_by, frozen_at from account.admin_freeze")
        .query(
            (rs, n) ->
                new Freeze(
                    rs.getString("reason"),
                    rs.getObject("frozen_by", UUID.class),
                    rs.getObject("frozen_at", OffsetDateTime.class)))
        .optional();
  }

  /** 변경 기록 한 줄. userId는 긴급 정지처럼 대상이 없으면 null. */
  public void record(
      UUID userId, String kind, String permission, String note, UUID by, Instant now) {
    jdbc.sql(
            "insert into account.admin_changes"
                + " (user_id, kind, permission, note, changed_by, changed_at)"
                + " values (:user, :kind, :p, :note, :by, :now)")
        .param("user", userId)
        .param("kind", kind)
        .param("p", permission)
        .param("note", note)
        .param("by", by)
        .param("now", Timestamp.from(now))
        .update();
  }

  /** 그 회원의 로그인(refresh token)을 모두 끊어요. */
  public int revokeLogins(UUID userId) {
    return jdbc.sql("delete from account.refresh_tokens where user_id = :id")
        .param("id", userId)
        .update();
  }

  /** 최근 변경 기록. */
  public List<Change> changes(Instant since, int limit) {
    return jdbc.sql(
            "select c.id, c.changed_at, c.user_id, u.nickname, c.kind, c.permission, c.note,"
                + " c.changed_by, b.nickname as by_nickname from account.admin_changes c"
                + " left join account.users u on u.id = c.user_id"
                + " left join account.users b on b.id = c.changed_by"
                + " where c.changed_at >= :since order by c.changed_at desc, c.id desc limit :limit")
        .param("since", Timestamp.from(since))
        .param("limit", limit)
        .query(
            (rs, n) ->
                new Change(
                    rs.getLong("id"),
                    rs.getTimestamp("changed_at").toInstant(),
                    rs.getObject("user_id", UUID.class),
                    rs.getString("nickname"),
                    rs.getString("kind"),
                    rs.getString("permission"),
                    rs.getString("note"),
                    rs.getObject("changed_by", UUID.class),
                    rs.getString("by_nickname")))
        .list();
  }
}
