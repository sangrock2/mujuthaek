package kr.mujuthaek.api.user.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import java.time.Clock;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import kr.mujuthaek.api.TestDatabase;
import kr.mujuthaek.api.benefit.service.BenefitQueryService;
import kr.mujuthaek.api.common.exception.CustomException;
import kr.mujuthaek.api.common.exception.ErrorCode;
import kr.mujuthaek.api.notice.service.NoticeQueryService;
import kr.mujuthaek.api.notice.service.NoticeSummary;
import kr.mujuthaek.api.user.repository.FavoriteRepository;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

/** 관심 200개 제한이 동시 저장에도 지켜지는지 (실제 DB, 요청마다 트랜잭션 하나). */
class FavoriteLimitConcurrencyTest {

  private final JdbcTemplate jdbc = new JdbcTemplate(TestDatabase.dataSource());
  private final TransactionTemplate tx =
      new TransactionTemplate(new DataSourceTransactionManager(TestDatabase.dataSource()));
  private final NoticeQueryService notices = mock(NoticeQueryService.class);
  private final FavoriteService service =
      new FavoriteService(
          new FavoriteRepository(JdbcClient.create(jdbc)),
          notices,
          mock(BenefitQueryService.class),
          Clock.systemUTC());

  @Test
  void concurrentSavesNeverGoOverTheLimit() throws Exception {
    // 2026-11-01 동시성 시험: 199개에서 서로 다른 공고 100개를 동시에 → 최대 204개, 성공 2~5개였어요
    when(notices.findSummary(any()))
        .thenAnswer(
            i ->
                Optional.of(
                    new NoticeSummary(
                        i.getArgument(0),
                        1,
                        "HOUSING",
                        "t",
                        null,
                        null,
                        "APPLYING",
                        null,
                        null,
                        List.of(),
                        false,
                        "/",
                        null)));
    UUID user = UUID.randomUUID();
    jdbc.update("insert into account.users (id) values (?)", user);
    for (int i = 0; i < FavoriteService.MAX_FAVORITES - 1; i++) {
      jdbc.update(
          "insert into account.favorites (user_id, target_type, target_id, created_at)"
              + " values (?, 'NOTICE', ?, now())",
          user,
          UUID.randomUUID());
    }

    int threads = 30;
    var pool = Executors.newFixedThreadPool(threads);
    var ready = new CountDownLatch(threads);
    var go = new CountDownLatch(1);
    List<Future<String>> results = new ArrayList<>();
    for (int i = 0; i < threads; i++) {
      results.add(
          pool.submit(
              () -> {
                ready.countDown();
                go.await();
                try {
                  tx.executeWithoutResult(s -> service.add(user, "NOTICE", UUID.randomUUID()));
                  return "saved";
                } catch (CustomException e) {
                  return e.errorCode().name();
                }
              }));
    }
    ready.await();
    go.countDown();
    List<String> outcomes = new ArrayList<>();
    for (var f : results) {
      outcomes.add(f.get(60, TimeUnit.SECONDS));
    }
    pool.shutdown();

    assertThat(
            jdbc.queryForObject(
                "select count(*) from account.favorites where user_id = ?", Long.class, user))
        .isEqualTo(FavoriteService.MAX_FAVORITES);
    assertThat(outcomes).filteredOn("saved"::equals).hasSize(1);
    assertThat(outcomes)
        .filteredOn(ErrorCode.FAVORITE_LIMIT_EXCEEDED.name()::equals)
        .hasSize(threads - 1);
  }
}
