package kr.mujuthaek.api.area.repository;

import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.sql.Array;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.Collection;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

/**
 * 세권·점수 계산 SQL(resources/area/calc/)을 읽고, 계산 대상 위치를 임시 테이블 {@code target_locations}에 담아요.
 *
 * <p>계산 SQL은 모두 이 임시 테이블과 조인해요. 트랜잭션이 끝나면 지워져요(on commit drop).
 */
final class AreaCalcSql {

  private static final String SQL_DIR = "area/calc/";
  private static final Map<String, String> CACHE = new ConcurrentHashMap<>();

  private AreaCalcSql() {}

  static String read(String name) {
    return CACHE.computeIfAbsent(
        name,
        n -> {
          try (InputStream in =
              AreaCalcSql.class.getClassLoader().getResourceAsStream(SQL_DIR + n)) {
            if (in == null) {
              throw new IllegalStateException("SQL 파일이 없어요: " + SQL_DIR + n);
            }
            return new String(in.readAllBytes(), StandardCharsets.UTF_8);
          } catch (IOException e) {
            throw new UncheckedIOException(e);
          }
        });
  }

  /** 트랜잭션 안(autoCommit false)에서 불러요. 목록이 null이면 좌표가 있는(OK·APPROX) 위치 전부예요. */
  static int fillTargets(Connection conn, Collection<UUID> locationIds) throws SQLException {
    try (Statement st = conn.createStatement()) {
      st.execute(
          "create temp table target_locations (location_id uuid primary key) on commit drop");
    }
    int n;
    if (locationIds == null) {
      try (Statement st = conn.createStatement()) {
        n =
            st.executeUpdate(
                "insert into target_locations select location_id from area.notice_locations"
                    + " where status in ('OK', 'APPROX')");
      }
    } else {
      Array ids = conn.createArrayOf("uuid", locationIds.toArray());
      try (PreparedStatement ps =
          conn.prepareStatement("insert into target_locations select distinct unnest(?::uuid[])")) {
        ps.setArray(1, ids);
        n = ps.executeUpdate();
      }
    }
    try (Statement st = conn.createStatement()) {
      // 임시 테이블은 자동 통계가 없어요. 대상이 많을 때 계획이 틀어지지 않게 직접 모아요.
      st.execute("analyze target_locations");
    }
    return n;
  }
}
