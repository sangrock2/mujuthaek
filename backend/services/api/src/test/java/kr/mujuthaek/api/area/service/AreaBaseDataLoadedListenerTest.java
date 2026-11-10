package kr.mujuthaek.api.area.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import java.io.ByteArrayInputStream;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import javax.sql.DataSource;
import kr.mujuthaek.api.area.AreaTestDatabase;
import kr.mujuthaek.api.area.domain.AreaSource;
import kr.mujuthaek.api.area.event.AreaBaseDataLoaded;
import kr.mujuthaek.api.area.repository.PostgresAreaBaseDataLoader;
import kr.mujuthaek.api.area.repository.S3AreaFileStore;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.stereotype.Component;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.event.TransactionalEventListener;

/**
 * 적재는 트랜잭션 밖에서 하지만, 세권·점수 계산이 {@code @TransactionalEventListener}로 AreaBaseDataLoaded를 받을 수 있는지.
 * 트랜잭션 없이 발행하면 이런 리스너는 아예 불리지 않아요.
 */
@SpringJUnitConfig(AreaBaseDataLoadedListenerTest.Config.class)
class AreaBaseDataLoadedListenerTest {

  @Configuration
  @EnableTransactionManagement
  static class Config {

    @Bean
    DataSource dataSource() {
      return AreaTestDatabase.dataSource();
    }

    @Bean
    PlatformTransactionManager transactionManager(DataSource dataSource) {
      return new DataSourceTransactionManager(dataSource);
    }

    @Bean
    S3AreaFileStore files() {
      return mock(S3AreaFileStore.class);
    }

    @Bean
    PostgresAreaBaseDataLoader loader() {
      return mock(PostgresAreaBaseDataLoader.class);
    }

    @Bean
    AreaSourceLoadService service(
        S3AreaFileStore files,
        PostgresAreaBaseDataLoader loader,
        org.springframework.context.ApplicationEventPublisher events,
        PlatformTransactionManager transactionManager) {
      return new AreaSourceLoadService(files, loader, events, transactionManager);
    }

    @Bean
    Recorder recorder() {
      return new Recorder();
    }
  }

  @Component
  static class Recorder {
    final List<AreaBaseDataLoaded> received = new CopyOnWriteArrayList<>();

    @TransactionalEventListener
    void on(AreaBaseDataLoaded event) {
      received.add(event);
    }
  }

  @Autowired AreaSourceLoadService service;
  @Autowired S3AreaFileStore files;
  @Autowired PostgresAreaBaseDataLoader loader;
  @Autowired Recorder recorder;

  @Test
  void transactionalListenersReceiveTheEventAfterCommit() {
    when(files.open(any())).thenReturn(new ByteArrayInputStream(new byte[0]));
    when(loader.load(any(), any())).thenReturn(AreaSourceLoadServiceTest.succeeded(3));

    service.load(AreaSourceLoadServiceTest.command());

    assertThat(recorder.received)
        .singleElement()
        .satisfies(e -> assertThat(e.source()).isEqualTo(AreaSource.STORES));
  }
}
