package kr.mujuthaek.api.area.repository;

import java.sql.Connection;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.Collection;
import java.util.UUID;
import javax.sql.DataSource;
import org.springframework.dao.DataAccessResourceFailureException;
import org.springframework.stereotype.Component;

/**
 * 공고 위치의 세권 지표(area.location_metrics)를 계산해요. 대상 위치 전체를 SQL 한 번으로 계산해서, 위치가 수천 곳이어도 왕복이 늘지 않아요.
 *
 * <p>대상 위치의 지표를 지우고 다시 넣는 게 한 트랜잭션이라, 계산 중 실패하면 이전 지표가 그대로 남아요. JDBC만 써서 테스트에서는 {@code new}로 만들어요.
 */
@Component
public final class PostgresLocationMetricsCalculator {

  private final DataSource dataSource;

  public PostgresLocationMetricsCalculator(DataSource dataSource) {
    this.dataSource = dataSource;
  }

  /** 주어진 위치만 다시 계산하고, 저장한 지표 줄 수를 돌려줘요. 좌표가 없는(FAILED) 위치는 지표를 지우기만 해요. */
  public int calculate(Collection<UUID> locationIds) {
    if (locationIds.isEmpty()) {
      return 0;
    }
    return run(locationIds);
  }

  /** 좌표가 있는 위치 전부를 다시 계산해요. 시설·상가를 다시 적재했을 때 써요. */
  public int calculateAll() {
    return run(null);
  }

  private int run(Collection<UUID> locationIds) {
    try (Connection conn = dataSource.getConnection()) {
      conn.setAutoCommit(false);
      try {
        AreaCalcSql.fillTargets(conn, locationIds);
        try (Statement st = conn.createStatement()) {
          st.execute(AreaCalcSql.read("metrics.sql"));
        }
        int rows;
        try (Statement st = conn.createStatement();
            ResultSet rs =
                st.executeQuery(
                    "select count(*) from area.location_metrics m"
                        + " join target_locations t using (location_id)")) {
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
      throw new DataAccessResourceFailureException("세권 지표를 계산하지 못했어요: " + e.getMessage(), e);
    }
  }
}
