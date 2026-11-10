package kr.mujuthaek.api.area.service;

import java.util.Collection;
import java.util.UUID;
import kr.mujuthaek.api.area.repository.PostgresLifeScoreCalculator;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

/**
 * 공고 위치의 생활권 항목 점수(area 6단계)를 다시 계산해요. 세권 지표(4단계)를 계산한 뒤에 불러요.
 *
 * <p>쓰는 규칙 버전은 설정 {@code mujuthaek.area.score-version}이에요. 버전을 바꾸면 {@link #recalculateAll()}로 전체를
 * 다시 계산해요.
 */
@Service
public class LifeScoreService {

  private static final Logger log = LoggerFactory.getLogger(LifeScoreService.class);

  private final PostgresLifeScoreCalculator calculator;
  private final String scoreVersion;

  public LifeScoreService(
      PostgresLifeScoreCalculator calculator,
      @Value("${mujuthaek.area.score-version}") String scoreVersion) {
    this.calculator = calculator;
    this.scoreVersion = scoreVersion;
  }

  public String scoreVersion() {
    return scoreVersion;
  }

  public int recalculate(Collection<UUID> locationIds) {
    int rows = calculator.calculate(locationIds, scoreVersion);
    log.info("생활권 점수 계산: 위치 {}곳, 점수 {}줄, 규칙 {}", locationIds.size(), rows, scoreVersion);
    return rows;
  }

  public int recalculateAll() {
    int rows = calculator.calculateAll(scoreVersion);
    log.info("생활권 점수 전체 계산: 점수 {}줄, 규칙 {}", rows, scoreVersion);
    return rows;
  }
}
