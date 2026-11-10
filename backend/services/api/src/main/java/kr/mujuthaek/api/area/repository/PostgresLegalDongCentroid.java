package kr.mujuthaek.api.area.repository;

import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Optional;
import javax.sql.DataSource;
import kr.mujuthaek.api.area.domain.Coordinate;
import org.springframework.dao.DataAccessResourceFailureException;
import org.springframework.stereotype.Component;

/**
 * 법정동코드의 대표점: 법정읍면동 경계(area.region_boundaries EMD, 앞 8자리)의 {@code st_pointonsurface}. 사전·검색 API로 못
 * 찾은 주소(건물 없는 개발 부지 등)를 대략 위치(APPROX)로 둘 때 써요. 리(10자리 끝이 00이 아님)는 그 읍·면의 점이에요.
 *
 * <p>무게중심 대신 표면 위 점을 써서, 오목하거나 여러 조각인 경계에서도 점이 늘 경계 안에 있어요. JDBC만 써서 테스트에서는 {@code new}로 만들어요.
 */
@Component
public final class PostgresLegalDongCentroid {

  private static final String SQL =
      """
      select st_y(p) as lat, st_x(p) as lng
      from (select st_pointonsurface(geom::geometry) as p from area.region_boundaries
            where level = 'EMD' and code = left(?, 8)) b
      """;

  private final DataSource dataSource;

  public PostgresLegalDongCentroid(DataSource dataSource) {
    this.dataSource = dataSource;
  }

  /** 경계가 없으면(적재 전, 없는 코드) 빈 값. */
  public Optional<Coordinate> find(String bjdCode) {
    if (bjdCode == null || !bjdCode.matches("[0-9]{10}")) {
      return Optional.empty();
    }
    try (Connection conn = dataSource.getConnection();
        PreparedStatement ps = conn.prepareStatement(SQL)) {
      ps.setString(1, bjdCode);
      try (ResultSet rs = ps.executeQuery()) {
        return rs.next()
            ? Optional.of(new Coordinate(rs.getDouble("lat"), rs.getDouble("lng")))
            : Optional.empty();
      }
    } catch (SQLException e) {
      throw new DataAccessResourceFailureException("법정동 대표점을 찾지 못했어요: " + e.getMessage(), e);
    }
  }

  /** 이름으로 찾은 대표점과 그 법정동코드(읍면동 경계 8자리 + 00). */
  public record Named(String bjdCode, Coordinate point) {}

  private static final String BY_NAME =
      """
      select code, st_y(p) as lat, st_x(p) as lng
      from (select code, st_pointonsurface(geom::geometry) as p from area.region_boundaries
            where level = 'EMD' and left(code, 5) = ? and name = ?) b
      limit 2
      """;

  /**
   * 주소의 법정동 이름으로 대표점 (공고가 법정동코드를 주지 않았을 때). 그 시군구 안에서 이름이 정확히 같은 읍면동 하나일 때만이에요(시군구 안 읍면동 이름은 겹치지
   * 않아요). 리가 붙은 이름(「낭산면 용기리」)은 앞의 읍·면으로 찾아요.
   */
  public Optional<Named> findByName(String sigunguCode, String dongName) {
    if (sigunguCode == null || !sigunguCode.matches("[0-9]{5}") || dongName == null) {
      return Optional.empty();
    }
    String name = dongName.strip().split("\\s+")[0];
    if (name.isEmpty()) {
      return Optional.empty();
    }
    try (Connection conn = dataSource.getConnection();
        PreparedStatement ps = conn.prepareStatement(BY_NAME)) {
      ps.setString(1, sigunguCode);
      ps.setString(2, name);
      try (ResultSet rs = ps.executeQuery()) {
        if (!rs.next()) {
          return Optional.empty();
        }
        Named found =
            new Named(
                rs.getString("code") + "00",
                new Coordinate(rs.getDouble("lat"), rs.getDouble("lng")));
        return rs.next() ? Optional.empty() : Optional.of(found);
      }
    } catch (SQLException e) {
      throw new DataAccessResourceFailureException("법정동 대표점을 찾지 못했어요: " + e.getMessage(), e);
    }
  }
}
