package kr.mujuthaek.api.area.service;

import java.util.List;
import java.util.Optional;
import kr.mujuthaek.api.area.domain.AddressMatch;
import kr.mujuthaek.api.area.domain.BoundaryCheck;
import kr.mujuthaek.api.area.domain.Coordinate;
import kr.mujuthaek.api.area.domain.GeocodeResult;
import kr.mujuthaek.api.area.domain.GeocodeResult.FailReason;
import kr.mujuthaek.api.area.geocode.AddressCoordinates;
import kr.mujuthaek.api.area.geocode.AddressParser;
import kr.mujuthaek.api.area.geocode.AddressSearch;
import kr.mujuthaek.api.area.geocode.CoordOutcome;
import kr.mujuthaek.api.area.geocode.JusoCandidates;
import kr.mujuthaek.api.area.geocode.JusoCandidates.Hint;
import kr.mujuthaek.api.area.geocode.JusoResult;
import kr.mujuthaek.api.area.geocode.ParsedAddress;
import kr.mujuthaek.api.area.geocode.ParsedAddress.Kind;
import kr.mujuthaek.api.area.geocode.SearchOutcome;
import kr.mujuthaek.api.area.repository.PostgresAddressPointLookup;
import kr.mujuthaek.api.area.repository.PostgresLegalDongCentroid;
import kr.mujuthaek.api.area.repository.PostgresRegionBoundaryCheck;
import kr.mujuthaek.api.area.repository.PostgresUtmkTransform;
import kr.mujuthaek.api.common.region.RegionQueryService;
import org.springframework.stereotype.Service;

/**
 * 공고 주소 글자 하나를 좌표로 바꿔요 (3단계). 틀린 좌표보다 대략 위치·못 찾음이 나아서, 단계마다 하나로 정해질 때만 받아요.
 *
 * <ol>
 *   <li>주소 정리 ({@link AddressParser})
 *   <li>시군구: 받은 법정동코드(2026 개편 전 코드는 지금 코드로) 앞 5자리, 없으면 주소의 시도·시군구 이름
 *   <li>도로명 주소면 도로명주소 사전 (FILE·FUZZY)
 *   <li>못 찾았거나 지번이면 도로명주소 검색 API → 결과 하나를 고르고 그 도로명·번호로 사전을 다시 (SEARCH_API). 지하 여부 0·1로 없으면 지하 여부를
 *       빼고 한 번 더 (사전의 섬 주소 코드 3). 사전에 아직 없는 새 건물이면 좌표제공 API (COORD_API)
 *   <li>그래도 없으면 법정동 대표점 (APPROX, CENTROID): 받은 법정동코드, 없으면 검색 API가 고른 결과의 법정동, 그것도 없으면 주소의 법정동 이름
 * </ol>
 *
 * <p>마지막에 찾은 좌표를 시군구·법정동 경계와 맞춰 봐요(3-4). 검색 API 키가 없는 환경은 그 단계를 건너뛰어요(오류 아님). 저장과 같은 주소 다시 안 찾기는 공고
 * 위치 저장(NoticeLocationService)에서 해요.
 */
@Service
public class AddressLocator {

  private final PostgresAddressPointLookup dictionary;
  private final AddressSearch search;
  private final AddressCoordinates coordinates;
  private final PostgresUtmkTransform utmk;
  private final PostgresLegalDongCentroid centroids;
  private final PostgresRegionBoundaryCheck boundaries;
  private final RegionQueryService regions;

  public AddressLocator(
      PostgresAddressPointLookup dictionary,
      AddressSearch search,
      AddressCoordinates coordinates,
      PostgresUtmkTransform utmk,
      PostgresLegalDongCentroid centroids,
      PostgresRegionBoundaryCheck boundaries,
      RegionQueryService regions) {
    this.dictionary = dictionary;
    this.search = search;
    this.coordinates = coordinates;
    this.utmk = utmk;
    this.centroids = centroids;
    this.boundaries = boundaries;
    this.regions = regions;
  }

  /**
   * @param address 공고 주소 글자
   * @param bjdCode 공고가 준 법정동코드 10자리 (없으면 null)
   */
  public GeocodeResult locate(String address, String bjdCode) {
    ParsedAddress parsed = AddressParser.parse(address == null ? "" : address);
    String bjd = currentBjd(bjdCode);
    String sigungu = bjd != null ? bjd.substring(0, 5) : sigunguByName(parsed);
    return checked(find(parsed, bjd, sigungu), bjd);
  }

  /**
   * 찾은 좌표를 경계와 맞춰 봐요(3-4): 시군구 경계에서 50m 넘게 밖이면 버리고(OUT_OF_REGION), 받은 법정동 경계 밖이면 표시만 해요. 시군구를 모르거나
   * 경계 자료가 없으면 검사하지 못해서 그대로 둬요.
   */
  private GeocodeResult checked(GeocodeResult result, String bjd) {
    if (result.coordinate() == null || result.sigunguCode() == null) {
      return result;
    }
    BoundaryCheck check =
        boundaries.check(
            result.sigunguCode(), bjd, result.coordinate().lat(), result.coordinate().lng());
    if (!check.passed()) {
      return GeocodeResult.failed(FailReason.OUT_OF_REGION, result.sigunguCode());
    }
    return check.emdMismatch() ? result.withRegionMismatch() : result;
  }

  private GeocodeResult find(ParsedAddress parsed, String bjd, String sigungu) {
    if (parsed.kind() == Kind.UNKNOWN && bjd == null) {
      return GeocodeResult.failed(FailReason.PARSE_FAILED, sigungu);
    }

    if (parsed.kind() == Kind.ROAD && sigungu != null) {
      Optional<AddressMatch> found =
          dictionary.find(
              sigungu,
              parsed.roadName(),
              parsed.underground() ? 1 : 0,
              parsed.buildingMain(),
              parsed.buildingSub());
      if (found.isPresent()) {
        return GeocodeResult.ok(found.get(), sigungu);
      }
    }

    boolean apiError = false;
    String searchedBjd = null;
    if (parsed.kind() == Kind.ROAD || parsed.kind() == Kind.JIBUN) {
      SearchOutcome outcome = search.search(parsed.normalized());
      switch (outcome) {
        case SearchOutcome.Found found -> {
          Optional<JusoResult> picked =
              JusoCandidates.pick(found.results(), hint(parsed, bjd, sigungu));
          if (picked.isPresent()) {
            JusoResult r = picked.get();
            Optional<AddressMatch> again = fromDictionary(r);
            String foundSigungu = sigungu != null ? sigungu : r.sigunguCode();
            if (again.isPresent()) {
              return GeocodeResult.bySearch(again.get(), foundSigungu);
            }
            // 사전에 아직 없는 새 건물: 좌표제공 API로 출입구 좌표 (키가 없거나 못 찾으면 대표점으로)
            switch (coordinates.coordinates(r)) {
              case CoordOutcome.Found c -> {
                return GeocodeResult.byCoordApi(
                    utmk.toWgs84(c.entX(), c.entY()), r.admCd(), foundSigungu);
              }
              case CoordOutcome.Failed f -> apiError = f.reason() != SearchOutcome.Reason.NO_KEY;
              case CoordOutcome.NotFound n -> {}
              case CoordOutcome.Rejected j -> {}
            }
            searchedBjd = r.admCd();
          }
        }
        case SearchOutcome.Failed failed ->
            apiError = failed.reason() != SearchOutcome.Reason.NO_KEY; // 키가 없으면 건너뛴 것
        case SearchOutcome.NotFound notFound -> {}
        case SearchOutcome.Rejected rejected -> {}
      }
    }

    String centroidBjd = bjd != null ? bjd : searchedBjd;
    Optional<Coordinate> point = centroids.find(centroidBjd);
    if (point.isPresent()) {
      return GeocodeResult.approx(point.get(), centroidBjd, sigungu);
    }
    // 법정동코드를 모르면 주소의 법정동 이름으로 (지번 주소의 동·리, 도로명 주소의 괄호 안 동)
    Optional<PostgresLegalDongCentroid.Named> named = centroids.findByName(sigungu, parsed.dong());
    if (named.isPresent()) {
      return GeocodeResult.approx(named.get().point(), named.get().bjdCode(), sigungu);
    }
    if (parsed.kind() == Kind.UNKNOWN) {
      return GeocodeResult.failed(FailReason.PARSE_FAILED, sigungu);
    }
    return GeocodeResult.failed(apiError ? FailReason.API_ERROR : FailReason.NOT_FOUND, sigungu);
  }

  /** 검색 API가 준 도로명·번호로 사전에서 정확히 (API 도로명은 정식 이름이라 오타 고치기는 안 받아요). */
  private Optional<AddressMatch> fromDictionary(JusoResult r) {
    if (r.sigunguCode() == null || r.rn() == null) {
      return Optional.empty();
    }
    Optional<AddressMatch> exact =
        dictionary
            .find(
                r.sigunguCode(), r.rn(), r.underground() ? 1 : 0, r.buildingMain(), r.buildingSub())
            .filter(m -> m.method() == AddressMatch.Method.FILE);
    return exact.isPresent()
        ? exact
        : dictionary.findAnyLevel(r.sigunguCode(), r.rn(), r.buildingMain(), r.buildingSub());
  }

  private static Hint hint(ParsedAddress parsed, String bjd, String sigungu) {
    boolean road = parsed.kind() == Kind.ROAD;
    return new Hint(
        bjd,
        sigungu,
        road ? parsed.roadName() : null,
        road ? parsed.buildingMain() : null,
        road ? parsed.buildingSub() : null);
  }

  /** 받은 법정동코드를 지금 코드로. 개편으로 여러 곳으로 갈라졌으면(어느 것인지 모름) null. */
  private String currentBjd(String bjdCode) {
    List<String> current = regions.toCurrent(bjdCode);
    return current.size() == 1 ? current.getFirst() : null;
  }

  /** 주소의 시도·시군구 이름으로 시군구 코드. 시군구 5자리로 하나로 정해질 때만. */
  private String sigunguByName(ParsedAddress parsed) {
    if (parsed.sigungu() == null) {
      return null;
    }
    String code = regions.resolve(parsed.sido(), parsed.sigungu()).code();
    return code != null && code.length() == 5 ? code : null;
  }
}
