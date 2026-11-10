package kr.mujuthaek.api.area;

import java.sql.Connection;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import org.flywaydb.core.Flyway;
import org.postgresql.ds.PGSimpleDataSource;
import org.testcontainers.postgresql.PostgreSQLContainer;
import org.testcontainers.utility.DockerImageName;

/**
 * area 테스트용 PostGIS. 스프링 없이 컨테이너 하나에 Flyway로 저장소의 마이그레이션을 모두 적용해요.
 *
 * <p>스키마 목록은 application.yml의 spring.flyway.schemas와 같아야 해요.
 */
public final class AreaTestDatabase {

  private static final DockerImageName POSTGIS =
      DockerImageName.parse("postgis/postgis:17-3.5").asCompatibleSubstituteFor("postgres");
  private static final String[] SCHEMAS = {
    "common",
    "notice",
    "benefit",
    "eligibility",
    "area",
    "account",
    "notification",
    "traffic",
    "chat"
  };

  private static PGSimpleDataSource dataSource;

  private AreaTestDatabase() {}

  /** 처음 부를 때 컨테이너를 띄우고 마이그레이션해요. 테스트 실행이 끝나면 Testcontainers가 정리해요. */
  public static synchronized PGSimpleDataSource dataSource() {
    if (dataSource == null) {
      var container = new PostgreSQLContainer(POSTGIS);
      container.start();
      var ds = new PGSimpleDataSource();
      ds.setUrl(container.getJdbcUrl());
      ds.setUser(container.getUsername());
      ds.setPassword(container.getPassword());
      Flyway.configure()
          .dataSource(ds)
          .schemas(SCHEMAS)
          .locations("classpath:db/migration")
          .load()
          .migrate();
      dataSource = ds;
    }
    return dataSource;
  }

  public static String one(String sql) throws SQLException {
    try (Connection c = dataSource().getConnection();
        Statement st = c.createStatement();
        ResultSet rs = st.executeQuery(sql)) {
      rs.next();
      return rs.getString(1);
    }
  }

  public static void exec(String sql) throws SQLException {
    try (Connection c = dataSource().getConnection();
        Statement st = c.createStatement()) {
      st.execute(sql);
    }
  }
}
