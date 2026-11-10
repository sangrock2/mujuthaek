package kr.mujuthaek.api.eligibility.service;

import static kr.mujuthaek.api.notice.NoticeApiFixture.schedule;

import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Clock;
import java.time.LocalDate;
import java.time.YearMonth;
import java.time.ZoneId;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import kr.mujuthaek.api.CountingDataSource;
import kr.mujuthaek.api.TestDatabase;
import kr.mujuthaek.api.area.repository.PostgresLocationScores;
import kr.mujuthaek.api.area.repository.PostgresNoticeLocations;
import kr.mujuthaek.api.area.repository.PostgresSiteDetails;
import kr.mujuthaek.api.area.service.NoticeAreaQueryService;
import kr.mujuthaek.api.common.region.RegionQueryService;
import kr.mujuthaek.api.eligibility.dto.request.ApplicantRequest;
import kr.mujuthaek.api.eligibility.dto.request.NoticeSearchRequest;
import kr.mujuthaek.api.eligibility.repository.CriteriaStore;
import kr.mujuthaek.api.eligibility.repository.LoanProductStore;
import kr.mujuthaek.api.notice.NoticeApiFixture;
import kr.mujuthaek.api.notice.NoticeFixtures;
import kr.mujuthaek.api.notice.repository.AreaScoreRepository;
import kr.mujuthaek.api.notice.repository.FollowUpRepository;
import kr.mujuthaek.api.notice.repository.NoticeQueries;
import kr.mujuthaek.api.notice.service.NoticeQueryService;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.simple.JdbcClient;
import tools.jackson.databind.JsonNode;

/**
 * 맞춤 목록 속도 측정 (PERF=1일 때만). 공고 300개에 실제 모양의 판정 틀을 넣고, 같은 조건으로 전체·시도·시군구·다음 페이지를 여러 번 불러 시간과 SQL 문
 * 수를 재요. 결과는 build/perf/notice-search.md에 써요.
 */
@EnabledIfEnvironmentVariable(named = "PERF", matches = "1")
class NoticeSearchPerfTest {

  private static final int RUNS = 20;
  private static final String[] SIGUNGUS = {
    "11440", "11650", "11500", "11110", "41135", "41465", "41281", "26350", "26500", "26260"
  };
  private static final String[] FRAMES = {
    "youth-safe-housing-balsan",
    "seoripul-artown",
    "assets-family-status",
    "income-bonuses",
    "long-term-jeonse-85plus",
    "rank-ladder-happy-housing"
  };

  private final NoticeApiFixture f = new NoticeApiFixture();

  @Test
  void measure() throws Exception {
    List<JsonNode> frames = new ArrayList<>();
    for (String name : FRAMES) {
      Path file = Path.of("src/test/resources/eligibility/frames/housing/" + name + ".json");
      frames.add(NoticeFixtures.JSON.readTree(Files.readString(file)).get("frame"));
    }
    for (int i = 0; i < 300; i++) {
      String sigungu = SIGUNGUS[i % SIGUNGUS.length];
      JsonNode frame = frames.get(i % frames.size());
      String end = LocalDate.of(2026, 11, 1).plusDays(i % 40).toString();
      f.notice(
          p -> {
            schedule(p, "2026-10-01", end);
            NoticeFixtures.region(p, sigungu);
            NoticeFixtures.judgment(p, frame);
          });
    }

    // 실제 서버처럼 커넥션 풀을 써요 (테스트 DB는 쿼리마다 새로 접속해서 시간이 부풀려져요)
    var db = TestDatabase.dataSource();
    var pool = new com.zaxxer.hikari.HikariDataSource();
    pool.setJdbcUrl(db.getUrl());
    pool.setUsername(db.getUser());
    pool.setPassword(db.getPassword());
    pool.setMaximumPoolSize(4);
    var counting = new CountingDataSource(pool);
    var jdbc = new JdbcTemplate(counting.dataSource());
    var client = JdbcClient.create(jdbc);
    Clock clock =
        Clock.fixed(
            NoticeApiFixture.TODAY.atStartOfDay(ZoneId.of("Asia/Seoul")).toInstant(),
            ZoneId.of("Asia/Seoul"));
    var queries =
        new NoticeQueryService(
            new NoticeQueries(jdbc),
            new FollowUpRepository(client),
            new AreaScoreRepository(client),
            new RegionQueryService(jdbc),
            new NoticeAreaQueryService(
                new PostgresNoticeLocations(counting.dataSource()),
                new PostgresSiteDetails(counting.dataSource()),
                new PostgresLocationScores(counting.dataSource())),
            clock,
            NoticeFixtures.JSON);
    var criteria =
        new CriteriaService(
            new CriteriaStore(jdbc), new LoanProductStore(jdbc), NoticeFixtures.JSON, clock);
    var evaluations =
        new NoticeEvaluationService(
            queries, criteria, new PrepareCostService(new LoanProductStore(jdbc), criteria, clock));
    var search =
        new NoticeSearchService(
            queries,
            evaluations,
            new kr.mujuthaek.api.eligibility.service.JudgingFrames(
                queries,
                new io.micrometer.core.instrument.simple.SimpleMeterRegistry(),
                20000,
                false));

    var applicant =
        new ApplicantRequest(
            null,
            YearMonth.of(1997, 3),
            "11440",
            true,
            1,
            0,
            List.of("YOUTH"),
            "SINGLE",
            null,
            0,
            false,
            "3_5",
            new ApplicantRequest.SubscriptionRequest("24_PLUS", 26),
            List.of(),
            Map.of(
                "MEDIAN_INCOME", new ApplicantRequest.PercentRange(100, 110, null),
                "URBAN_WORKER_INCOME", new ApplicantRequest.PercentRange(80, 90, 2025)),
            null,
            2026,
            new ApplicantRequest.WonRange(25_000_000L, 50_000_000L),
            null,
            List.of());
    var all = request(null, applicant, null);
    String next = search.search(all).nextCursor();

    StringBuilder out = new StringBuilder();
    out.append("| 경우 | 후보 수 | 중앙값 ms | 상위 5% ms | SQL 문 수 |\n|---|---|---|---|---|\n");
    out.append(row("전체 (300)", search, counting, all));
    out.append(row("서울 11", search, counting, request(List.of("11"), applicant, null)));
    out.append(row("마포 11440", search, counting, request(List.of("11440"), applicant, null)));
    out.append(row("다음 페이지", search, counting, request(null, applicant, next)));

    Path report = Path.of("build/perf/notice-search.md");
    Files.createDirectories(report.getParent());
    Files.writeString(report, out.toString());
    System.out.println(out);
    pool.close();
  }

  private NoticeSearchRequest request(
      List<String> regions, ApplicantRequest applicant, String cursor) {
    return new NoticeSearchRequest(
        new NoticeSearchRequest.Filters(null, regions, null, null, List.of(f.provider), null, null),
        applicant,
        null,
        true,
        cursor,
        20);
  }

  private static String row(
      String name, NoticeSearchService search, CountingDataSource counting, NoticeSearchRequest r) {
    for (int i = 0; i < 3; i++) {
      search.search(r); // 예열
    }
    long[] ms = new long[RUNS];
    int candidates = 0;
    int statements = 0;
    for (int i = 0; i < RUNS; i++) {
      counting.reset();
      long start = System.nanoTime();
      var res = search.search(r);
      ms[i] = (System.nanoTime() - start) / 1_000_000;
      statements = counting.statements();
      var c = res.counts();
      candidates = c.eligible() + c.needsInput() + c.ineligible();
    }
    java.util.Arrays.sort(ms);
    return "| %s | %d | %d | %d | %d |%n"
        .formatted(
            name, candidates, ms[RUNS / 2], ms[(int) Math.ceil(RUNS * 0.95) - 1], statements);
  }
}
