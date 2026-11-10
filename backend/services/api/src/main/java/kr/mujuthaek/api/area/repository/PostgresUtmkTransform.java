package kr.mujuthaek.api.area.repository;

import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;
import kr.mujuthaek.api.area.domain.Coordinate;
import org.springframework.dao.DataAccessResourceFailureException;
import org.springframework.stereotype.Component;

/**
 * UTM-K(EPSG:5179, 미터) 좌표를 경위도(EPSG:4326)로. 도로명주소 좌표제공 API의 entX·entY에 써요. 도로명주소 적재
 * (area/load/address_entrance.sql)와 같은 PostGIS 변환이라 사전 좌표와 어긋나지 않아요.
 */
@Component
public final class PostgresUtmkTransform {

  private static final String SQL =
      "select st_y(g) as lat, st_x(g) as lng"
          + " from (select st_transform(st_setsrid(st_makepoint(?, ?), 5179), 4326) as g) p";

  private final DataSource dataSource;

  public PostgresUtmkTransform(DataSource dataSource) {
    this.dataSource = dataSource;
  }

  public Coordinate toWgs84(double x, double y) {
    try (Connection conn = dataSource.getConnection();
        PreparedStatement ps = conn.prepareStatement(SQL)) {
      ps.setDouble(1, x);
      ps.setDouble(2, y);
      try (ResultSet rs = ps.executeQuery()) {
        rs.next();
        return new Coordinate(rs.getDouble("lat"), rs.getDouble("lng"));
      }
    } catch (SQLException e) {
      throw new DataAccessResourceFailureException("좌표를 바꾸지 못했어요: " + e.getMessage(), e);
    }
  }
}
