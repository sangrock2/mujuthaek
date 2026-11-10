package kr.mujuthaek.api.common.region;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.time.LocalDate;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;
import org.springframework.transaction.support.TransactionTemplate;

/**
 * api가 뜰 때 빌드에 들어간 법정동코드표가 DB에 넣은 것보다 새로우면 넣어요. 같은 판이면 아무것도 안 해요.
 *
 * <p>여러 인스턴스가 동시에 떠도 한 번만 넣게, 트랜잭션 advisory lock을 잡고 기준일을 다시 본 뒤 넣어요. 끄려면 {@code
 * mujuthaek.regions.load-on-startup=false}.
 */
@Component
@ConditionalOnProperty(
    name = "mujuthaek.regions.load-on-startup",
    havingValue = "true",
    matchIfMissing = true)
class RegionStartupLoader implements ApplicationRunner {

  private static final Logger log = LoggerFactory.getLogger(RegionStartupLoader.class);

  private final RegionLoader loader;
  private final JdbcTemplate jdbc;
  private final TransactionTemplate tx;

  RegionStartupLoader(RegionLoader loader, JdbcTemplate jdbc, TransactionTemplate tx) {
    this.loader = loader;
    this.jdbc = jdbc;
    this.tx = tx;
  }

  @Override
  public void run(ApplicationArguments args) throws Exception {
    loadIfNewer();
  }

  /**
   * @return 넣었으면 true
   */
  boolean loadIfNewer() throws Exception {
    LocalDate bundled = RegionLoader.bundled().baseDate();
    Boolean loaded =
        tx.execute(
            status -> {
              jdbc.queryForObject(
                  "select pg_advisory_xact_lock(hashtext('common.regions.load'))", Object.class);
              LocalDate current =
                  jdbc.queryForObject("select max(base_date) from common.regions", LocalDate.class);
              if (current != null && !current.isBefore(bundled)) {
                return false;
              }
              try {
                loader.loadBundled();
              } catch (IOException e) {
                throw new UncheckedIOException(e);
              }
              return true;
            });
    if (Boolean.TRUE.equals(loaded)) {
      log.info("지역 코드표를 {} 판으로 넣었어요", bundled);
    }
    return Boolean.TRUE.equals(loaded);
  }
}
