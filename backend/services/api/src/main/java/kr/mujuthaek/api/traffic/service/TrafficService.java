package kr.mujuthaek.api.traffic.service;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import kr.mujuthaek.api.common.cache.RecentCache;
import kr.mujuthaek.api.traffic.TrafficProperties;
import kr.mujuthaek.api.traffic.dto.BotTrafficResponse;
import kr.mujuthaek.api.traffic.dto.RealtimeResponse;
import kr.mujuthaek.api.traffic.dto.TrafficResponse;
import kr.mujuthaek.api.traffic.dto.TrafficResponse.Daily;
import kr.mujuthaek.api.traffic.dto.TrafficResponse.FunnelStep;
import kr.mujuthaek.api.traffic.dto.TrafficResponse.Item;
import kr.mujuthaek.api.traffic.dto.TrafficResponse.NoticeView;
import kr.mujuthaek.api.traffic.ga.GaDataClient;
import kr.mujuthaek.api.traffic.ga.GaDataClient.ReportSpec;
import kr.mujuthaek.api.traffic.ga.GaDataClient.Row;
import kr.mujuthaek.api.traffic.log.RequestLogStore;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

/** 관리자 트래픽 화면: GA 보고서(기간별로 한 시간쯤 다시 씀)와 api 서버 요청 기록을 모아요. */
@Service
public class TrafficService {

  private static final Logger log = LoggerFactory.getLogger(TrafficService.class);

  /** 이용 흐름 단계(프론트가 보내는 GA 이벤트, 판정 입력값 같은 개인 정보는 싣지 않음). session_start는 GA 기본 이벤트. */
  static final List<String[]> FUNNEL =
      List.of(
          new String[] {"session_start", "방문"},
          new String[] {"conditions_complete", "조건 입력 완료"},
          new String[] {"judgment_run", "판정 실행"},
          new String[] {"notice_source_open", "원문 보기"},
          new String[] {"notice_bookmark", "관심 등록"});

  static final List<ReportSpec> REPORTS =
      List.of(
          new ReportSpec(
              List.of("date"),
              List.of("activeUsers", "newUsers", "sessions", "screenPageViews"),
              null,
              0,
              null,
              null),
          item("sessionDefaultChannelGroup", "sessions"),
          item("sessionSource", "sessions"),
          item("sessionCampaignName", "sessions"),
          item("landingPage", "sessions"),
          item("pagePath", "screenPageViews"),
          item("deviceCategory", "activeUsers"),
          item("browser", "activeUsers"),
          item("region", "activeUsers"),
          new ReportSpec(
              List.of("eventName"),
              List.of("eventCount", "totalUsers"),
              "eventCount",
              0,
              FUNNEL.stream().map(f -> f[0]).toList(),
              null),
          // 공고 상세 페이지(/notices/{id})별 조회 → 인기 공고. 한 공고의 하위 경로까지 넉넉히 받아 공고별로 합쳐요
          new ReportSpec(
              List.of("pagePath"),
              List.of("screenPageViews", "activeUsers"),
              "screenPageViews",
              100,
              null,
              "/notices/"));

  /** 공고 상세 주소에서 공고 ID (/notices/{id}, 뒤의 하위 경로·쿼리는 같은 공고) */
  private static final Pattern NOTICE_PATH = Pattern.compile("^/notices/([^/?#]+)");

  /** 실시간은 30초만 다시 써요(같은 화면을 여러 번 열어도 GA를 매번 부르지 않게). */
  private static final Duration REALTIME_TTL = Duration.ofSeconds(30);

  /**
   * 서버 요청 기록 집계는 1분만 다시 써요. 기록 전체를 세는 쿼리라 화면을 열 때마다 돌리면 DB가 바빠져요(2026-10-29 부하 시험: 관리자 50명에서
   * 9~12초).
   */
  static final Duration SERVER_TTL = Duration.ofMinutes(1);

  /** 마지막으로 받은 실시간 숫자(GA 실패 때 대신 보여 줘요). */
  private volatile RealtimeResponse lastRealtime;

  private final GaDataClient ga;
  private final RequestLogStore logs;
  private final TrafficProperties props;
  private final Clock clock;

  /**
   * 기간별 GA 보고서(cacheTtl, 한 시간쯤). 만료된 순간 여러 명이 열어도 GA는 한 번만 불러요(GA 호출 한도). 실패는 남기지 않아서 다음 요청이 다시
   * 물어요.
   */
  private final RecentCache<Integer, TrafficResponse.Ga> gaReports;

  /** 기간별 마지막으로 받은 GA 보고서(GA 실패 때 대신 보여 줘요). */
  private final Map<Integer, TrafficResponse.Ga> lastGa = new ConcurrentHashMap<>();

  /** 실시간 숫자(30초). 키는 하나예요. */
  private final RecentCache<Boolean, RealtimeResponse> realtimeReports;

  /** 기간(days)별 서버 숫자. 같은 기간을 동시에 열면 집계는 한 번이에요. */
  private final RecentCache<Integer, List<RequestLogStore.ServerDaily>> serverDaily;

  private final RecentCache<Integer, BotTrafficResponse> botsCache;

  public TrafficService(
      GaDataClient ga, RequestLogStore logs, TrafficProperties props, Clock clock) {
    this.ga = ga;
    this.logs = logs;
    this.props = props;
    this.clock = clock;
    this.serverDaily = new RecentCache<>(SERVER_TTL, clock, this::serverDailyNow);
    this.botsCache = new RecentCache<>(SERVER_TTL, clock, this::botsNow);
    this.gaReports =
        new RecentCache<>(props.ga().cacheTtl(), clock, days -> fetchGa(days, clock.instant()));
    this.realtimeReports = new RecentCache<>(REALTIME_TTL, clock, any -> fetchRealtime());
  }

  private static ReportSpec item(String dimension, String metric) {
    // 주 값이 활성 사용자면 사용자 수도 그 값이에요(측정항목 하나만 물어요)
    List<String> metrics =
        "activeUsers".equals(metric) ? List.of(metric) : List.of(metric, "activeUsers");
    return new ReportSpec(List.of(dimension), metrics, metric, 10, null, null);
  }

  /** 개요·유입·이용 흐름(GA)과 서버 숫자. 서버 숫자는 1분 안이면 지난 집계를 써요. */
  public TrafficResponse traffic(int days) {
    Instant now = clock.instant();
    return new TrafficResponse(now, days, gaReport(days), serverDaily.get(days));
  }

  private List<RequestLogStore.ServerDaily> serverDailyNow(int days) {
    Instant now = clock.instant();
    LocalDate today = LocalDate.ofInstant(now, RequestLogStore.KST);
    Instant from = today.minusDays(days - 1L).atStartOfDay(RequestLogStore.KST).toInstant();
    return logs.daily(from, now.plusSeconds(1));
  }

  /** 봇·보안. 1분 안이면 지난 집계를 그대로 줘요(asOf가 그 집계 시각). */
  public BotTrafficResponse bots(int days) {
    return botsCache.get(days);
  }

  private BotTrafficResponse botsNow(int days) {
    Instant now = clock.instant();
    LocalDate today = LocalDate.ofInstant(now, RequestLogStore.KST);
    Instant from = today.minusDays(days - 1L).atStartOfDay(RequestLogStore.KST).toInstant();
    Instant to = now.plusSeconds(1);
    return new BotTrafficResponse(
        now,
        days,
        logs.clientsDaily(from, to),
        logs.topSources(from, to, 20),
        logs.topBotPaths(from, to, 15),
        logs.statuses(from, to),
        logs.adminAccess(from, to, 50),
        logs.loginFailures(from, to, 30));
  }

  private TrafficResponse.Ga gaReport(int days) {
    if (!ga.configured()) {
      return TrafficResponse.Ga.off("GA가 연결되지 않았어요(속성 ID·서비스 계정 키 설정 필요)");
    }
    try {
      TrafficResponse.Ga result = gaReports.get(days);
      lastGa.put(days, result);
      return result;
    } catch (RuntimeException failure) {
      log.warn("GA 보고서를 가져오지 못했어요: {}", failure.getMessage());
      // 실패해도 지난번 값이 있으면 그걸 보여 줘요
      TrafficResponse.Ga last = lastGa.get(days);
      return last != null ? last : TrafficResponse.Ga.off("GA 숫자를 가져오지 못했어요. 잠시 뒤 다시 열어 주세요");
    }
  }

  private TrafficResponse.Ga fetchGa(int days, Instant now) {
    List<List<Row>> r = ga.run(REPORTS, days);
    return new TrafficResponse.Ga(
        true,
        null,
        now,
        r.get(0).stream().map(TrafficService::daily).toList(),
        items(r.get(1)),
        items(r.get(2)),
        items(r.get(3)),
        items(r.get(4)),
        items(r.get(5)),
        items(r.get(6)),
        items(r.get(7)),
        items(r.get(8)),
        funnel(r.get(9)),
        popularNotices(r.get(10)));
  }

  /** 지금 접속자: 최근 30분·5분 활성 사용자와 기기별. */
  public RealtimeResponse realtime() {
    if (!ga.configured()) {
      return RealtimeResponse.off("GA가 연결되지 않았어요(속성 ID·서비스 계정 키 설정 필요)");
    }
    try {
      RealtimeResponse result = realtimeReports.get(true);
      lastRealtime = result;
      return result;
    } catch (RuntimeException failure) {
      log.warn("GA 실시간 보고서를 가져오지 못했어요: {}", failure.getMessage());
      RealtimeResponse last = lastRealtime;
      return last != null ? last : RealtimeResponse.off("GA 실시간 숫자를 가져오지 못했어요");
    }
  }

  private RealtimeResponse fetchRealtime() {
    Instant now = clock.instant();
    long last30 = total(ga.realtime(List.of(), List.of("activeUsers"), null));
    long last5 = total(ga.realtime(List.of(), List.of("activeUsers"), 5));
    List<Item> devices =
        ga.realtime(List.of("deviceCategory"), List.of("activeUsers"), null).stream()
            .map(
                r ->
                    new Item(
                        r.dimensions().getFirst(), r.metrics().getFirst(), r.metrics().getFirst()))
            .sorted((x, y) -> Long.compare(y.value(), x.value()))
            .toList();
    return new RealtimeResponse(true, null, now, last30, last5, devices);
  }

  private static long total(List<Row> rows) {
    return rows.stream().mapToLong(r -> r.metrics().getFirst()).sum();
  }

  /** 공고 상세 경로별 조회를 공고 ID로 합쳐 많이 본 순 10개. */
  static List<NoticeView> popularNotices(List<Row> rows) {
    Map<String, long[]> byNotice = new LinkedHashMap<>();
    for (Row row : rows) {
      Matcher m = NOTICE_PATH.matcher(row.dimensions().getFirst());
      if (!m.find()) {
        continue;
      }
      long[] sum = byNotice.computeIfAbsent(m.group(1), k -> new long[2]);
      sum[0] += row.metrics().get(0);
      sum[1] += row.metrics().get(1);
    }
    return byNotice.entrySet().stream()
        .map(e -> new NoticeView(e.getKey(), e.getValue()[0], e.getValue()[1]))
        .sorted((x, y) -> Long.compare(y.views(), x.views()))
        .limit(10)
        .toList();
  }

  private static Daily daily(Row row) {
    LocalDate date = LocalDate.parse(row.dimensions().getFirst(), DateTimeFormatter.BASIC_ISO_DATE);
    List<Long> m = row.metrics();
    return new Daily(date, m.get(0), m.get(1), m.get(2), m.get(3));
  }

  private static List<Item> items(List<Row> rows) {
    return rows.stream()
        .map(
            r ->
                new Item(
                    r.dimensions().getFirst(),
                    r.metrics().get(0),
                    r.metrics().get(r.metrics().size() > 1 ? 1 : 0)))
        .toList();
  }

  private static List<FunnelStep> funnel(List<Row> rows) {
    return FUNNEL.stream()
        .map(
            f -> {
              Row row =
                  rows.stream()
                      .filter(r -> f[0].equals(r.dimensions().getFirst()))
                      .findFirst()
                      .orElse(null);
              return new FunnelStep(
                  f[0],
                  f[1],
                  row == null ? 0 : row.metrics().get(0),
                  row == null ? 0 : row.metrics().get(1));
            })
        .toList();
  }
}
