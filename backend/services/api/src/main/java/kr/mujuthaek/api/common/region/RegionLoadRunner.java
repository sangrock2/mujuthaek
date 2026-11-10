package kr.mujuthaek.api.common.region;

import java.nio.file.Path;
import java.time.LocalDate;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

/**
 * 저장소 법정동코드표는 뜰 때 알아서 넣어요(RegionStartupLoader). 저장소에 아직 없는 판을 먼저 넣어 보고 싶을 때만, 파일 경로를 주고 api를 띄우면 그
 * 파일로 적재해요(탭·쉼표, UTF-8·CP949 모두).
 *
 * <pre>
 * ./gradlew bootRun --args='--mujuthaek.regions.load-file=/path/법정동코드 전체자료.txt --mujuthaek.regions.base-date=2026-07-01'
 * </pre>
 */
@Component
@ConditionalOnProperty("mujuthaek.regions.load-file")
class RegionLoadRunner implements ApplicationRunner {

  private final RegionLoader loader;
  private final Path file;
  private final LocalDate baseDate;

  RegionLoadRunner(
      RegionLoader loader,
      @Value("${mujuthaek.regions.load-file}") Path file,
      @Value("${mujuthaek.regions.base-date}") LocalDate baseDate) {
    this.loader = loader;
    this.file = file;
    this.baseDate = baseDate;
  }

  @Override
  public void run(ApplicationArguments args) throws Exception {
    loader.load(file, baseDate);
  }
}
