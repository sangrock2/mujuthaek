package kr.mujuthaek.api.notice.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;

import java.time.Clock;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import kr.mujuthaek.api.TestDatabase;
import kr.mujuthaek.api.benefit.service.BenefitQueryService;
import kr.mujuthaek.api.common.exception.CustomException;
import kr.mujuthaek.api.common.exception.ErrorCode;
import kr.mujuthaek.api.notice.client.ExtractionReviewClient;
import kr.mujuthaek.api.notice.dto.request.GeneralReportRequest;
import kr.mujuthaek.api.notice.repository.NoticeReportRepository;
import kr.mujuthaek.api.notice.service.internal.NoticeReportService;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

/** 실제 PostgreSQL 트랜잭션에서 동시 제출이 일일 상한을 넘지 않는지 검사해요. */
class ReportQuotaIntegrationTest {
  @Test
  void concurrentReportsAtNineteenReserveOnlyOneRemainingSlot() throws Exception {
    var source = TestDatabase.dataSource();
    var jdbc = JdbcClient.create(source);
    var transaction = new TransactionTemplate(new JdbcTransactionManager(source));
    var service =
        new NoticeReportService(
            new NoticeReportRepository(jdbc),
            mock(ExtractionReviewClient.class),
            event -> {},
            Clock.systemUTC(),
            mock(BenefitQueryService.class));
    UUID reporter = UUID.randomUUID();
    var request = new GeneralReportRequest("ETC", "합성 동시성 검사", null, null);
    try {
      for (int i = 0; i < 19; i++) {
        transaction.executeWithoutResult(
            status -> service.reportGeneral(request, reporter.toString()));
      }
      var ready = new CountDownLatch(8);
      var start = new CountDownLatch(1);
      List<Future<Boolean>> results = new ArrayList<>();
      try (var pool = Executors.newFixedThreadPool(8)) {
        for (int i = 0; i < 8; i++) {
          results.add(
              pool.submit(
                  () -> {
                    ready.countDown();
                    if (!start.await(10, TimeUnit.SECONDS))
                      throw new IllegalStateException("start timeout");
                    try {
                      transaction.executeWithoutResult(
                          status -> service.reportGeneral(request, reporter.toString()));
                      return true;
                    } catch (CustomException e) {
                      if (e.errorCode() != ErrorCode.RATE_LIMITED) throw e;
                      return false;
                    }
                  }));
        }
        assertThat(ready.await(10, TimeUnit.SECONDS)).isTrue();
        start.countDown();
        int accepted = 0;
        for (Future<Boolean> result : results) if (result.get(10, TimeUnit.SECONDS)) accepted++;
        assertThat(accepted).isEqualTo(1);
      } finally {
        start.countDown();
      }
      assertThat(
              jdbc.sql("select count(*) from notice.notice_reports where reporter_id = :id")
                  .param("id", reporter)
                  .query(Integer.class)
                  .single())
          .isEqualTo(20);
    } finally {
      jdbc.sql("delete from notice.notice_reports where reporter_id = :id")
          .param("id", reporter)
          .update();
    }
  }
}
