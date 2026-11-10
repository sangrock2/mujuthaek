package kr.mujuthaek.api.area.service;

import java.util.Collection;
import java.util.UUID;
import kr.mujuthaek.api.area.repository.PostgresLocationMetricsCalculator;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

/**
 * 공고 위치의 세권 지표(area 4단계)를 다시 계산해요.
 *
 * <p>언제 부르나: 위치의 좌표가 새로 생기거나 바뀌면 그 위치만, 시설·상가를 다시 적재하면({@code AreaBaseDataLoaded}) 전체. 지금 규모(단지 수천
 * 곳)는 전체 다시 계산으로 충분해요. {@code @Transactional}을 붙이지 않아요: 계산기가 커넥션을 직접 잡고 커밋해요.
 */
@Service
public class LocationMetricsService {

  private static final Logger log = LoggerFactory.getLogger(LocationMetricsService.class);

  private final PostgresLocationMetricsCalculator calculator;

  public LocationMetricsService(PostgresLocationMetricsCalculator calculator) {
    this.calculator = calculator;
  }

  public int recalculate(Collection<UUID> locationIds) {
    int rows = calculator.calculate(locationIds);
    log.info("세권 지표 계산: 위치 {}곳, 지표 {}줄", locationIds.size(), rows);
    return rows;
  }

  public int recalculateAll() {
    long started = System.nanoTime();
    int rows = calculator.calculateAll();
    log.info("세권 지표 전체 계산: 지표 {}줄, {}ms", rows, (System.nanoTime() - started) / 1_000_000);
    return rows;
  }
}
