package kr.mujuthaek.api.common.config;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.*;

import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.ResultSetMetaData;
import java.util.HashMap;
import javax.sql.DataSource;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.hibernate.autoconfigure.HibernatePropertiesCustomizer;
import org.springframework.boot.jdbc.autoconfigure.JdbcClientAutoConfiguration;
import org.springframework.boot.jdbc.autoconfigure.JdbcTemplateAutoConfiguration;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.simple.JdbcClient;

class DatabaseQueryBudgetConfigTest {
  private ApplicationContextRunner context(DataSource dataSource) {
    return new ApplicationContextRunner()
        .withConfiguration(
            AutoConfigurations.of(
                JdbcTemplateAutoConfiguration.class, JdbcClientAutoConfiguration.class))
        .withUserConfiguration(DatabaseQueryBudgetConfig.class)
        .withBean(DataSource.class, () -> dataSource)
        .withPropertyValues("spring.jdbc.template.query-timeout=${API_QUERY_TIMEOUT:15s}");
  }

  @Test
  void bootJdbcClientUsesTheBudgetOnItsActualPreparedStatementAndJpaUsesMilliseconds()
      throws Exception {
    var source = mock(DataSource.class);
    var connection = mock(Connection.class);
    var statement = mock(PreparedStatement.class);
    var rows = mock(ResultSet.class);
    var metadata = mock(ResultSetMetaData.class);
    when(source.getConnection()).thenReturn(connection);
    when(connection.prepareStatement(anyString())).thenReturn(statement);
    when(statement.executeQuery()).thenReturn(rows);
    when(rows.getMetaData()).thenReturn(metadata);
    when(metadata.getColumnCount()).thenReturn(1);
    when(rows.next()).thenReturn(true, false);
    when(rows.getInt(1)).thenReturn(7);
    context(source)
        .run(
            app -> {
              assertThat(app).hasNotFailed();
              assertThat(app.getBean(JdbcTemplate.class).getQueryTimeout()).isEqualTo(15);
              assertThat(
                      app.getBean(JdbcClient.class)
                          .sql("select :value")
                          .param("value", 7)
                          .query(Integer.class)
                          .single())
                  .isEqualTo(7);
              verify(statement).setQueryTimeout(15);
              var properties = new HashMap<String, Object>();
              app.getBean(HibernatePropertiesCustomizer.class).customize(properties);
              assertThat(properties.get("jakarta.persistence.query.timeout")).isEqualTo(15000);
              // No connection-wide statement_timeout is installed: direct JDBC/Flyway receives the
              // same unmodified datasource.
              verify(connection, never()).createStatement();
            });
  }

  @Test
  void configuredBudgetIsSharedByJdbcAndJpa() {
    context(mock(DataSource.class))
        .withPropertyValues("API_QUERY_TIMEOUT=3s")
        .run(
            app -> {
              assertThat(app).hasNotFailed();
              assertThat(app.getBean(JdbcTemplate.class).getQueryTimeout()).isEqualTo(3);
              var properties = new HashMap<String, Object>();
              app.getBean(HibernatePropertiesCustomizer.class).customize(properties);
              assertThat(properties.get("jakarta.persistence.query.timeout")).isEqualTo(3000);
            });
  }

  @Test
  void valuesWhichWouldDisableOrOverflowTheBudgetFailStartup() {
    for (String budget : new String[] {"0s", "-1s", "500ms", "30d"}) {
      context(mock(DataSource.class))
          .withPropertyValues("API_QUERY_TIMEOUT=" + budget)
          .run(app -> assertThat(app).hasFailed());
    }
  }
}
