package kr.mujuthaek.api.area.service;

import java.util.UUID;
import kr.mujuthaek.api.area.domain.GeocodeResult;
import kr.mujuthaek.api.area.domain.NoticeLocation;
import kr.mujuthaek.api.area.geocode.AddressParser;
import kr.mujuthaek.api.area.repository.PostgresNoticeLocations;
import org.springframework.stereotype.Service;

/**
 * 공고 위치 하나의 좌표를 찾아 area.notice_locations에 저장해요 (3단계 마지막). 같은 주소(정리한 주소 키)·같은 법정동코드로 이미 정확히 찾았으면(OK)
 * 다시 찾지 않고 그 좌표를 써요 — 검색 API·좌표제공 API 하루 한도를 아끼고, 같은 단지의 공고가 여러 번 와도 좌표가 같게요.
 *
 * <p>공고 이벤트(NoticeLocationsChanged)를 받아 이걸 부르는 건 연결 PR이에요.
 */
@Service
public class NoticeLocationService {

  private final AddressLocator locator;
  private final PostgresNoticeLocations locations;

  public NoticeLocationService(AddressLocator locator, PostgresNoticeLocations locations) {
    this.locator = locator;
    this.locations = locations;
  }

  /** 저장한 area 위치 ID와 결과. */
  public record Located(UUID locationId, GeocodeResult result, boolean reused) {}

  public Located locate(NoticeLocation location) {
    String key = addressKey(location.address());
    var reused = locations.reusable(key, location.bjdCode()); // 찾기 입력(주소·법정동코드)이 같을 때만
    GeocodeResult result =
        reused.orElseGet(() -> locator.locate(location.address(), location.bjdCode()));
    UUID id = locations.save(location, key, result);
    return new Located(id, result, reused.isPresent());
  }

  /** 정리한 주소 글자 (띄어쓰기·괄호 안 안내 등을 정리한 것). 주소가 없으면 null — 다시 찾기 판단에 쓰지 않아요. */
  static String addressKey(String address) {
    if (address == null || address.isBlank()) {
      return null;
    }
    String normalized = AddressParser.parse(address).normalized();
    return normalized == null || normalized.isBlank() ? null : normalized;
  }
}
