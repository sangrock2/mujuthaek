package kr.mujuthaek.api.area.service;

import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;
import java.time.LocalDate;
import java.util.UUID;
import java.util.function.BiFunction;
import kr.mujuthaek.api.area.domain.AreaLoadReport;
import kr.mujuthaek.api.area.domain.AreaLoadRequest;
import kr.mujuthaek.api.area.domain.AreaSource;
import kr.mujuthaek.api.area.event.AreaBaseDataLoaded;
import kr.mujuthaek.api.area.repository.PostgresAreaBaseDataLoader;
import kr.mujuthaek.api.area.repository.S3AreaFileStore;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

/**
 * S3에 올라온 원천 파일 하나를 area 기초 데이터로 적재해요.
 *
 * <p>{@code @Transactional}을 붙이지 않아요: 적재기가 커넥션을 직접 잡고 커밋·롤백해서, 실패해도 실행 기록(load_runs)이 남아야 해요. 데이터가
 * 바뀌면 {@link AreaBaseDataLoaded}를 알려요.
 */
@Service
public class AreaSourceLoadService {

  private static final Logger log = LoggerFactory.getLogger(AreaSourceLoadService.class);

  private final S3AreaFileStore files;
  private final PostgresAreaBaseDataLoader loader;
  private final ApplicationEventPublisher events;
  private final TransactionTemplate transaction;

  public AreaSourceLoadService(
      S3AreaFileStore files,
      PostgresAreaBaseDataLoader loader,
      ApplicationEventPublisher events,
      PlatformTransactionManager transactionManager) {
    this.files = files;
    this.loader = loader;
    this.events = events;
    this.transaction = new TransactionTemplate(transactionManager);
  }

  /**
   * @param scope 상가정보는 시도 이름(강원, 경기 …), 나머지는 "ALL"
   * @param s3Key area/{source}/{기준일}/{영문 파일 이름}
   * @param sha256 collector가 올릴 때 계산한 파일 지문
   */
  public record Command(
      AreaSource source,
      String scope,
      String s3Key,
      String sha256,
      LocalDate dataDate,
      boolean allowShrink) {}

  /** 파일 문제(칸 없음, 잘린 파일 등)는 FAILED 결과로, S3·DB 연결 문제는 예외로 알려요. */
  public AreaLoadReport load(Command c) {
    return load(c, loader::load);
  }

  /**
   * 대기열에서 꺼낸 실행 기록(RUNNING, {@link AreaLoadWorker})을 이어 써서 적재해요. 결과와 예외는 {@link #load(Command)}와
   * 같아요.
   */
  public AreaLoadReport loadQueued(UUID runId, Command c) {
    return load(c, (request, in) -> loader.loadRun(runId, request, in));
  }

  private AreaLoadReport load(
      Command c, BiFunction<AreaLoadRequest, InputStream, AreaLoadReport> loadFile) {
    var request =
        new AreaLoadRequest(
            c.source(), c.scope(), c.s3Key(), c.sha256(), c.dataDate(), c.allowShrink());
    AreaLoadReport report;
    try (InputStream in = files.open(c.s3Key())) {
      report = loadFile.apply(request, in);
    } catch (IOException e) {
      throw new UncheckedIOException(e);
    }
    log.info(
        "area 적재 {} {} {}: 읽음 {}, 넣음 {}, 바꿈 {}, 지움 {}, 거름 {} {}",
        c.source(),
        request.scope(),
        report.status(),
        report.rowsIn(),
        report.rowsInserted(),
        report.rowsUpdated(),
        report.rowsDeleted(),
        report.rowsRejected(),
        report.rejectReasons());
    if (report.status() == AreaLoadReport.Status.FAILED) {
      log.warn("area 적재 실패 {} {}: {}", c.source(), request.scope(), report.error());
    }
    if (report.changedData()) {
      // 적재는 트랜잭션 밖에서 끝났어요. 받는 쪽이 트랜잭션 리스너여도 불리게, 발행만 짧은 트랜잭션 안에서 해요.
      var loaded = new AreaBaseDataLoaded(c.source(), request.scope(), report.runId());
      transaction.executeWithoutResult(status -> events.publishEvent(loaded));
    }
    return report;
  }
}
