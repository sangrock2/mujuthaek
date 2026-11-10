package kr.mujuthaek.api.area.repository;

import java.math.BigDecimal;
import java.sql.Array;
import java.util.Arrays;
import java.util.List;
import java.util.Optional;
import javax.sql.DataSource;
import kr.mujuthaek.api.area.domain.Piecewise;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

/** 점수 규칙(area.score_rules) 읽기. 요청 때 매기는 점수(직장 거리 등)를 저장된 규칙과 같은 구간으로 매겨요. */
@Component
public final class PostgresScoreRules {

  private final JdbcTemplate jdbc;

  public PostgresScoreRules(DataSource dataSource) {
    this.jdbc = new JdbcTemplate(dataSource);
  }

  /** 규칙 버전·지표의 구간. 없으면 빈 값. */
  public Optional<Piecewise> rule(String scoreVersion, String metric) {
    return jdbc
        .query(
            "select xs, ys from area.score_rules where score_version = ? and metric = ?",
            (rs, n) -> new Piecewise(decimals(rs.getArray("xs")), decimals(rs.getArray("ys"))),
            scoreVersion,
            metric)
        .stream()
        .findFirst();
  }

  private static List<BigDecimal> decimals(Array array) throws java.sql.SQLException {
    return Arrays.stream((Object[]) array.getArray()).map(v -> (BigDecimal) v).toList();
  }
}
