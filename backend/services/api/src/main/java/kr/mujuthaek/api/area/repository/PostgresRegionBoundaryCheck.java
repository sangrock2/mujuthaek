package kr.mujuthaek.api.area.repository;

import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;
import kr.mujuthaek.api.area.domain.BoundaryCheck;
import kr.mujuthaek.api.area.domain.BoundaryCheck.Sigungu;
import org.springframework.dao.DataAccessResourceFailureException;
import org.springframework.stereotype.Component;

/**
 * 좌표를 area.region_boundaries의 시군구·법정읍면동 경계와 맞춰 봐요. 여러 조각·구멍 있는 경계도 그대로 다뤄요(구멍 안은 그 구역이 아님).
 *
 * <p>도로명주소 원천에서 좌표가 동쪽으로 밀린 줄(34줄)처럼 사전 좌표가 틀린 경우도 여기서 걸러요. JDBC만 써서 테스트에서는 {@code new}로 만들어요.
 */
@Component
public final class PostgresRegionBoundaryCheck {

  private static final String SQL =
      """
      select (select bool_or(st_dwithin(b.geom, p.g, ?)) from area.region_boundaries b
               where b.level = 'SIG' and b.code = ?) as sig,
             (select bool_or(st_dwithin(b.geom, p.g, ?)) from area.region_boundaries b
               where b.level = 'EMD' and b.code = left(?, 8)) as emd
      from (select st_setsrid(st_makepoint(?, ?), 4326)::geography as g) p
      """;

  private final DataSource dataSource;

  public PostgresRegionBoundaryCheck(DataSource dataSource) {
    this.dataSource = dataSource;
  }

  /**
   * @param sigunguCode 시군구 코드 5자리
   * @param bjdCode 받은 법정동코드 10자리 (없으면 null — 법정동 검사는 건너뜀)
   */
  public BoundaryCheck check(String sigunguCode, String bjdCode, double lat, double lng) {
    try (Connection conn = dataSource.getConnection();
        PreparedStatement ps = conn.prepareStatement(SQL)) {
      ps.setInt(1, BoundaryCheck.TOLERANCE_METERS);
      ps.setString(2, sigunguCode);
      ps.setInt(3, BoundaryCheck.TOLERANCE_METERS);
      ps.setString(4, bjdCode);
      ps.setDouble(5, lng);
      ps.setDouble(6, lat);
      try (ResultSet rs = ps.executeQuery()) {
        rs.next();
        Boolean sig = (Boolean) rs.getObject("sig");
        Boolean emd = (Boolean) rs.getObject("emd");
        Sigungu sigungu =
            sig == null ? Sigungu.NO_BOUNDARY : sig ? Sigungu.INSIDE : Sigungu.OUT_OF_REGION;
        return new BoundaryCheck(sigungu, Boolean.FALSE.equals(emd));
      }
    } catch (SQLException e) {
      throw new DataAccessResourceFailureException("경계 검사를 하지 못했어요: " + e.getMessage(), e);
    }
  }
}
