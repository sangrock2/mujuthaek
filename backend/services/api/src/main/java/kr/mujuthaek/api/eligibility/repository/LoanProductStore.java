package kr.mujuthaek.api.eligibility.repository;

import java.sql.Array;
import java.sql.SQLException;
import java.util.Arrays;
import java.util.List;
import kr.mujuthaek.api.eligibility.rule.PrepareCost.LoanProduct;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

/** eligibility.loan_products 읽기 (쓰고 있는 상품만). */
@Repository
public class LoanProductStore {

  private final JdbcTemplate jdbc;

  public LoanProductStore(JdbcTemplate jdbc) {
    this.jdbc = jdbc;
  }

  public List<LoanProduct> enabled() {
    return jdbc.query(
        """
        select code, name, max_amount_won, deposit_ratio, max_annual_income_won, max_total_assets_won,
               min_age, max_age, target_groups
        from eligibility.loan_products where enabled order by code
        """,
        (rs, i) ->
            new LoanProduct(
                rs.getString(1),
                rs.getString(2),
                rs.getLong(3),
                rs.getBigDecimal(4),
                (Long) rs.getObject(5),
                (Long) rs.getObject(6),
                (Integer) rs.getObject(7),
                (Integer) rs.getObject(8),
                strings(rs.getArray(9))));
  }

  private static List<String> strings(Array array) throws SQLException {
    return array == null ? List.of() : Arrays.asList((String[]) array.getArray());
  }
}
