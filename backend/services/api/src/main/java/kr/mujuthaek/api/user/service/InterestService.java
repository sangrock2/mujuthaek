package kr.mujuthaek.api.user.service;

import java.time.Clock;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import java.util.regex.Pattern;
import kr.mujuthaek.api.common.exception.CustomException;
import kr.mujuthaek.api.common.exception.ErrorCode;
import kr.mujuthaek.api.common.region.RegionQueryService;
import kr.mujuthaek.api.user.repository.InterestRepository;
import kr.mujuthaek.api.user.repository.InterestRepository.Business;
import kr.mujuthaek.api.user.repository.InterestRepository.Housing;
import kr.mujuthaek.api.user.repository.InterestRepository.Support;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 관심 조건 (contracts/schemas/user-preferences.draft.md 2-2~2-4). 저장하면 새 공고·정책 알림 대상이 되고, 지우면 빠져요 (관심
 * 공고 알림은 그대로).
 *
 * <p>지역은 시군구 5자리 또는 시도 전체 xx000이고 common.regions에 있는 유효한 코드만 받아요. 업종·창업 단계·지원 종류는 v1에서 저장만 하고 알림
 * 대상을 고를 때는 지역·전국 여부(주거는 공고 유형까지)만 써요.
 */
@Service
public class InterestService {

  static final int MAX_REGIONS = 30;
  static final int MAX_TYPES = 30;
  static final Pattern REGION = Pattern.compile("\\d{5}");
  static final Pattern NOTICE_TYPE = Pattern.compile("[A-Z][A-Z0-9_]{0,39}");
  static final Set<String> INDUSTRIES =
      Set.of(
          "A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M", "N", "O", "P", "Q", "R",
          "S", "T", "U");
  static final Set<String> STARTUP_STAGES = Set.of("PRE_STARTUP", "OPERATING");
  static final Set<String> SUPPORT_KINDS =
      Set.of("RENT", "DEPOSIT_LOAN", "PURCHASE_LOAN", "HOUSING_SUPPLY", "MOVE_IN_GRANT", "CASH");

  private final InterestRepository interests;
  private final RegionQueryService regions;
  private final Clock clock;

  public InterestService(InterestRepository interests, RegionQueryService regions, Clock clock) {
    this.interests = interests;
    this.regions = regions;
    this.clock = clock;
  }

  @Transactional(readOnly = true)
  public Optional<Housing> housing(UUID userId) {
    return interests.housing(userId);
  }

  @Transactional(readOnly = true)
  public Optional<Business> business(UUID userId) {
    return interests.business(userId);
  }

  @Transactional(readOnly = true)
  public Optional<Support> support(UUID userId) {
    return interests.support(userId);
  }

  @Transactional
  public Housing saveHousing(UUID userId, Housing h) {
    Housing checked =
        new Housing(
            regions(h.regionCodes()),
            h.includeNationwide(),
            values("noticeTypes", h.noticeTypes(), v -> NOTICE_TYPE.matcher(v).matches()));
    interests.saveHousing(userId, checked, clock.instant());
    return checked;
  }

  @Transactional
  public Business saveBusiness(UUID userId, Business b) {
    Business checked =
        new Business(
            regions(b.regionCodes()),
            b.includeNationwide(),
            values("industryCodes", b.industryCodes(), INDUSTRIES::contains),
            values("startupStages", b.startupStages(), STARTUP_STAGES::contains));
    interests.saveBusiness(userId, checked, clock.instant());
    return checked;
  }

  @Transactional
  public Support saveSupport(UUID userId, Support s) {
    Support checked =
        new Support(
            regions(s.regionCodes()),
            s.includeNationwide(),
            values("supportKinds", s.supportKinds(), SUPPORT_KINDS::contains));
    interests.saveSupport(userId, checked, clock.instant());
    return checked;
  }

  /** kind: housing · business · support. 지우면 그 종류의 새 소식을 받지 않아요 */
  @Transactional
  public void delete(UUID userId, String kind) {
    interests.delete(table(kind), userId);
  }

  static String table(String kind) {
    return switch (kind) {
      case "housing" -> "housing_interests";
      case "business" -> "business_interests";
      case "support" -> "support_interests";
      default -> throw new CustomException(ErrorCode.NOT_FOUND);
    };
  }

  /** 중복은 한 번만, 순서는 그대로. 시도 전체는 시도 코드(앞 2자리)가, 시군구는 그 코드가 유효해야 해요 */
  private List<String> regions(List<String> codes) {
    List<String> distinct = distinct("regionCodes", codes, MAX_REGIONS);
    for (String code : distinct) {
      if (!REGION.matcher(code).matches()) {
        throw invalid("regionCodes", "시군구 5자리 또는 시도 전체 xx000이에요");
      }
      boolean wholeSido = code.endsWith("000");
      String lookup = wholeSido ? code.substring(0, 2) : code;
      boolean ok =
          regions
              .find(lookup)
              .filter(r -> r.valid() && r.level().equals(wholeSido ? "SIDO" : "SIGUNGU"))
              .isPresent();
      if (!ok) {
        throw invalid("regionCodes", "없거나 폐지된 지역 코드예요: " + code);
      }
    }
    return distinct;
  }

  private static List<String> values(
      String field, List<String> values, java.util.function.Predicate<String> allowed) {
    List<String> distinct = distinct(field, values, MAX_TYPES);
    for (String v : distinct) {
      if (!allowed.test(v)) {
        throw invalid(field, "모르는 값이에요: " + v);
      }
    }
    return distinct;
  }

  private static List<String> distinct(String field, List<String> values, int max) {
    if (values == null) {
      return List.of();
    }
    List<String> distinct =
        List.copyOf(
            new LinkedHashSet<>(values.stream().map(v -> v == null ? "" : v.strip()).toList()));
    if (distinct.size() > max) {
      throw invalid(field, max + "개까지예요");
    }
    return distinct;
  }

  private static CustomException invalid(String field, String reason) {
    return new CustomException(ErrorCode.VALIDATION_FAILED, field + ": " + reason);
  }
}
