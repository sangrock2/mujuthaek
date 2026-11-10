package kr.mujuthaek.api.common.region;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.IOException;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicInteger;
import kr.mujuthaek.api.TestDatabase;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

class RegionStartupLoaderTest {

  private final JdbcTemplate jdbc = new JdbcTemplate(TestDatabase.dataSource());
  private final TransactionTemplate tx =
      new TransactionTemplate(new DataSourceTransactionManager(TestDatabase.dataSource()));
  private final AtomicInteger loads = new AtomicInteger();
  private final RegionLoader countingLoader =
      new RegionLoader(jdbc) {
        @Override
        public int loadBundled() throws IOException {
          loads.incrementAndGet();
          return super.loadBundled();
        }
      };

  @BeforeEach
  void clean() {
    jdbc.update("delete from common.region_code_changes");
    jdbc.update("update common.regions set replaced_by = null");
    jdbc.update("delete from common.regions where level = 'SIGUNGU'");
    jdbc.update("delete from common.regions");
  }

  @Test
  void loadsOnlyWhenTheBundledFileIsNewer() throws Exception {
    RegionStartupLoader startup = new RegionStartupLoader(countingLoader, jdbc, tx);

    assertThat(startup.loadIfNewer()).isTrue(); // 비어 있음 → 넣음
    assertThat(startup.loadIfNewer()).isFalse(); // 같은 판 → 안 넣음

    jdbc.update("update common.regions set base_date = ?", LocalDate.of(2025, 1, 1));
    assertThat(startup.loadIfNewer()).isTrue(); // 예전 판 → 다시 넣음
    assertThat(loads).hasValue(2);
  }

  @Test
  void manyInstancesStartingTogetherLoadOnce() throws Exception {
    int instances = 4;
    ExecutorService pool = Executors.newFixedThreadPool(instances);
    CountDownLatch start = new CountDownLatch(1);
    List<Future<Boolean>> results = new ArrayList<>();
    for (int i = 0; i < instances; i++) {
      RegionStartupLoader startup = new RegionStartupLoader(countingLoader, jdbc, tx);
      Callable<Boolean> run =
          () -> {
            start.await();
            return startup.loadIfNewer();
          };
      results.add(pool.submit(run));
    }
    start.countDown();
    int loaded = 0;
    for (Future<Boolean> r : results) {
      loaded += r.get() ? 1 : 0;
    }
    pool.shutdown();

    assertThat(loaded).isEqualTo(1);
    assertThat(loads).hasValue(1);
    assertThat(
            jdbc.queryForObject(
                "select count(*) from common.regions where level = 'SIDO' and valid",
                Integer.class))
        .isEqualTo(16);
  }
}
