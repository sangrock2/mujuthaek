package kr.mujuthaek.api.area.repository;

import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.Collection;
import java.util.UUID;
import javax.sql.DataSource;
import org.springframework.dao.DataAccessResourceFailureException;
import org.springframework.stereotype.Component;

/**
 * 공고 위치의 생활권 항목 점수 5개(교통·학군·공원·편의·병원)를 저장된 세권 지표와 점수 규칙으로 계산해요(area.location_scores).
 *
 * <p>대상 위치의 LIFE 점수를 지우고 다시 넣는 게 한 트랜잭션이에요. 지표가 먼저 계산돼 있어야 해요. JDBC만 써서 테스트에서는 {@code new}로 만들어요.
 */
@Component
public final class PostgresLifeScoreCalculator {

  private final DataSource dataSource;

  public PostgresLifeScoreCalculator(DataSource dataSource) {
    this.dataSource = dataSource;
  }

  /** 주어진 위치만 다시 계산하고, 저장한 점수 줄 수를 돌려줘요. */
  public int calculate(Collection<UUID> locationIds, String scoreVersion) {
    if (locationIds.isEmpty()) {
      return 0;
    }
    return run(locationIds, scoreVersion);
  }

  /** 좌표가 있는 위치 전부를 다시 계산해요. 규칙 버전을 바꾸거나 지표를 전부 다시 계산했을 때 써요. */
  public int calculateAll(String scoreVersion) {
    return run(null, scoreVersion);
  }

  private int run(Collection<UUID> locationIds, String scoreVersion) {
    try (Connection conn = dataSource.getConnection()) {
      conn.setAutoCommit(false);
      try {
        requireVersion(conn, scoreVersion);
        AreaCalcSql.fillTargets(conn, locationIds);
        try (PreparedStatement ps = conn.prepareStatement(AreaCalcSql.read("life_scores.sql"))) {
          ps.setString(1, scoreVersion);
          ps.execute();
        }
        int rows;
        try (Statement st = conn.createStatement();
            ResultSet rs =
                st.executeQuery(
                    "select count(*) from area.location_scores s"
                        + " join target_locations t using (location_id) where s.score_kind = 'LIFE'")) {
          rs.next();
          rows = rs.getInt(1);
        }
        conn.commit();
        return rows;
      } catch (SQLException | RuntimeException e) {
        conn.rollback();
        throw e;
      }
    } catch (SQLException e) {
      throw new DataAccessResourceFailureException("생활권 점수를 계산하지 못했어요: " + e.getMessage(), e);
    }
  }

  /** 없는 버전이면 점수가 전부 지워지기만 해요. 설정 실수를 조용히 넘기지 않게 막아요. */
  private static void requireVersion(Connection conn, String scoreVersion) throws SQLException {
    try (PreparedStatement ps =
        conn.prepareStatement(
            "select exists (select 1 from area.score_weights"
                + " where score_version = ? and score_kind = 'LIFE')")) {
      ps.setString(1, scoreVersion);
      try (ResultSet rs = ps.executeQuery()) {
        rs.next();
        if (!rs.getBoolean(1)) {
          throw new IllegalArgumentException("점수 규칙 버전이 없어요: " + scoreVersion);
        }
      }
    }
  }
}
