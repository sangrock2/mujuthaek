package kr.mujuthaek.api.area.service;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;
import java.util.stream.Collectors;
import kr.mujuthaek.api.area.domain.AreaSource;
import kr.mujuthaek.api.area.domain.GeocodeResult;
import kr.mujuthaek.api.area.domain.GeocodeResult.FailReason;
import kr.mujuthaek.api.area.domain.GeocodeResult.Status;
import kr.mujuthaek.api.area.domain.NoticeLocation;
import kr.mujuthaek.api.area.domain.StoredLocation;
import kr.mujuthaek.api.area.domain.TotalScore;
import kr.mujuthaek.api.area.repository.PostgresLocationScores;
import kr.mujuthaek.api.area.repository.PostgresNoticeLocations;
import kr.mujuthaek.api.area.repository.PostgresNoticeLocations.RetryLocation;
import kr.mujuthaek.api.common.event.AreaScoresCalculated;
import kr.mujuthaek.api.common.event.NoticeLocationsChanged;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;

/**
 * 공고와 area를 이어요 (연결 PR). notice가 보낸 공고 위치로 좌표(3단계) → 세권 지표(4단계) → 생활권 점수(6단계)를 계산하고, 위치별 생활 점수를
 * {@link AreaScoresCalculated}로 돌려줘요(notice가 공고 상세 areaSummaries로 보여요).
 *
 * <ul>
 *   <li>주소·법정동코드가 그대로인 위치는 좌표를 다시 찾지 않고 공고 버전만 올려요 (같은 이벤트를 두 번 받아도, 위치 말고 다른 것만 바뀐 새 버전이어도)
 *   <li>좌표가 저장된 뒤 중단돼도 지표·점수를 다시 계산해요
 *   <li>이번 목록에 없는 위치(새 버전에서 빠짐)는 지워요. 지표·점수도 같이 지워져요
 *   <li>생활 점수(LIVING) = 생활권 항목 5개의 같은 비중 총점. 상업 점수(COMMERCIAL)는 업종이 있어야 해서 요청 때 계산하고 보내지 않아요
 * </ul>
 *
 * <p>area는 다른 모듈을 부르지 않아서, 공고 테이블 외래 키 대신 이벤트로 위치를 맞춰요.
 */
@Service
public class NoticeAreaLinkService {

  private static final Logger log = LoggerFactory.getLogger(NoticeAreaLinkService.class);
  static final String LIVING = "LIVING";

  private final NoticeLocationService locator;
  private final PostgresNoticeLocations locations;
  private final LocationMetricsService metrics;
  private final LifeScoreService lifeScores;
  private final PostgresLocationScores scores;
  private final ApplicationEventPublisher events;

  public NoticeAreaLinkService(
      NoticeLocationService locator,
      PostgresNoticeLocations locations,
      LocationMetricsService metrics,
      LifeScoreService lifeScores,
      PostgresLocationScores scores,
      ApplicationEventPublisher events) {
    this.locator = locator;
    this.locations = locations;
    this.metrics = metrics;
    this.lifeScores = lifeScores;
    this.scores = scores;
    this.events = events;
  }

  /** Resolve addresses before taking a database lock. */
  Map<String, NoticeLocationService.Lookup> resolve(NoticeLocationsChanged event, Runnable renew) {
    Map<String, StoredLocation> before = currentById(event.noticeId());
    Map<String, NoticeLocationService.Lookup> resolved = new LinkedHashMap<>();
    for (NoticeLocationsChanged.Location l : event.locations()) {
      renew.run();
      StoredLocation old = before.get(l.locationId());
      if (old == null || !unchanged(old, l)) {
        resolved.put(
            l.locationId(),
            locator.resolve(
                new NoticeLocation(
                    event.noticeId(),
                    event.noticeVersion(),
                    l.locationId(),
                    l.kind(),
                    l.address(),
                    l.regionCode())));
      }
    }
    return resolved;
  }

  /** The worker fences this write against the publication pointer and claim token. */
  void store(NoticeLocationsChanged event, Map<String, NoticeLocationService.Lookup> resolved) {
    Map<String, StoredLocation> current = currentById(event.noticeId());
    var ids = event.locations().stream().map(NoticeLocationsChanged.Location::locationId).toList();
    locations.deleteMissing(event.noticeId(), ids);
    for (NoticeLocationsChanged.Location l : event.locations()) {
      StoredLocation existing = current.get(l.locationId());
      if (existing != null && unchanged(existing, l)) {
        locations.touchVersion(existing.locationId(), event.noticeVersion());
      } else {
        var lookup = resolved.get(l.locationId());
        if (lookup == null) {
          throw new IllegalStateException("Location changed after resolution");
        }
        locator.save(lookup);
      }
    }
  }

  /** Work that stopped after committing coordinates can repeat this calculation. */
  void refresh(NoticeLocationsChanged event) {
    List<StoredLocation> stored = locations.ofNotice(event.noticeId());
    List<UUID> ids = stored.stream().map(StoredLocation::locationId).toList();
    metrics.recalculate(ids);
    lifeScores.recalculate(ids);
    publishScores(event.noticeId(), event.noticeVersion(), stored);
  }

  private Map<String, StoredLocation> currentById(UUID noticeId) {
    return locations.ofNotice(noticeId).stream()
        .collect(Collectors.toMap(StoredLocation::noticeLocationId, location -> location));
  }

  /**
   * 시설·상가를 다시 적재하면 세권 지표가 바뀌어서 전체를 다시 계산하고 공고마다 점수를 다시 보내요. 도로명주소·경계 적재는 지표에 쓰지 않아서 건너뛰어요.
   *
   * @return 다시 계산했으면 true
   */
  public boolean onBaseDataLoaded(AreaSource source) {
    if (source.target() != AreaSource.Target.FACILITIES
        && source.target() != AreaSource.Target.STORES) {
      return false;
    }
    metrics.recalculateAll();
    lifeScores.recalculateAll();
    Map<UUID, List<StoredLocation>> byNotice =
        locations.withCoordinates().stream()
            .collect(
                Collectors.groupingBy(
                    StoredLocation::noticeId, LinkedHashMap::new, Collectors.toList()));
    byNotice.forEach(
        (noticeId, list) ->
            publishScores(
                noticeId,
                list.stream().mapToInt(StoredLocation::noticeVersion).max().orElseThrow(),
                list));
    log.info("기초 데이터({}) 다시 적재로 세권·점수 전체 계산, 공고 {}건에 점수를 다시 보냄", source, byNotice.size());
    return true;
  }

  /** 좌표를 못 찾은 위치 (관리자 화면 데이터, 최근 순). */
  public List<StoredLocation> failedLocations(int limit) {
    return locations.failed(limit);
  }

  void completeGeocodeRetry(RetryLocation retry, GeocodeResult result) {
    // 자동 복구는 동 중심점이나 도로명 오타 추정으로 새 핀을 만들지 않아요.
    if (result.status() == Status.APPROX
        || result.method() == GeocodeResult.Method.FUZZY
        || result.regionMismatch()) {
      return;
    }
    NoticeLocation source = retry.location();
    if (!locations.completeGeocodeRetry(
            retry, NoticeLocationService.addressKey(source.address()), result)
        || result.coordinate() == null) {
      return;
    }
    var ids = List.of(retry.locationId());
    metrics.recalculate(ids);
    lifeScores.recalculate(ids);
    publishScores(
        source.noticeId(),
        source.noticeVersion(),
        locations.ofNotice(source.noticeId()).stream()
            .filter(location -> location.noticeVersion() == source.noticeVersion())
            .toList());
  }

  /** 주소·법정동코드가 같고, 지난번이 나중에 다시 하면 될 실패(API_ERROR)가 아니면 그대로예요. */
  private static boolean unchanged(StoredLocation old, NoticeLocationsChanged.Location l) {
    boolean retry = old.status() == Status.FAILED && old.failReason() == FailReason.API_ERROR;
    return !retry
        && Objects.equals(old.addressText(), l.address() == null ? "" : l.address())
        && Objects.equals(old.bjdCodeGiven(), l.regionCode());
  }

  private void publishScores(UUID noticeId, int noticeVersion, List<StoredLocation> stored) {
    List<StoredLocation> located = stored.stream().filter(s -> s.coordinate() != null).toList();
    var life = scores.lifeScores(located.stream().map(StoredLocation::locationId).toList());
    List<AreaScoresCalculated.Score> out = new ArrayList<>();
    for (StoredLocation s : located) {
      var l = life.get(s.locationId());
      if (l == null || l.scores().isEmpty()) {
        continue;
      }
      out.add(
          new AreaScoresCalculated.Score(
              s.noticeLocationId(),
              LIVING,
              TotalScore.of(l.scores(), Map.of()),
              l.calculatedAt(),
              l.scoreVersion()));
    }
    if (!out.isEmpty()) {
      events.publishEvent(new AreaScoresCalculated(noticeId, noticeVersion, out));
    }
  }
}
