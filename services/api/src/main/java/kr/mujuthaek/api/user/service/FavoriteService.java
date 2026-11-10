package kr.mujuthaek.api.user.service;

import java.time.Clock;
import java.time.Instant;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import kr.mujuthaek.api.benefit.service.BenefitQueryService;
import kr.mujuthaek.api.benefit.service.BenefitSummary;
import kr.mujuthaek.api.common.dto.response.CursorPageResponse;
import kr.mujuthaek.api.common.exception.CustomException;
import kr.mujuthaek.api.common.exception.ErrorCode;
import kr.mujuthaek.api.common.pagination.CursorKey;
import kr.mujuthaek.api.common.pagination.CursorQuery;
import kr.mujuthaek.api.common.text.ScreenPaths;
import kr.mujuthaek.api.notice.service.NoticeQueryService;
import kr.mujuthaek.api.notice.service.NoticeSummary;
import kr.mujuthaek.api.notice.service.PolicySummary;
import kr.mujuthaek.api.user.dto.response.FavoriteResponse;
import kr.mujuthaek.api.user.repository.FavoriteRepository;
import kr.mujuthaek.api.user.repository.FavoriteRepository.Favorite;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 관심 공고·관심 정책 (contracts/schemas/user-preferences.draft.md 2-1). 저장한 공고의 정정·후속 안내·마감 D-3·D-1 알림을
 * 받아요.
 *
 * <p>저장할 때 그 모듈 조회 메서드로 있는지 확인해요 (다른 모듈 테이블이라 FK가 없어서). 다른 공고에 합쳐진 공고는 남은 공고로 저장해요.
 */
@Service
public class FavoriteService {

  public static final int MAX_FAVORITES = 200;
  static final String SORT = "LATEST";

  private final FavoriteRepository favorites;
  private final NoticeQueryService notices;
  private final BenefitQueryService benefits;
  private final Clock clock;

  public FavoriteService(
      FavoriteRepository favorites,
      NoticeQueryService notices,
      BenefitQueryService benefits,
      Clock clock) {
    this.favorites = favorites;
    this.notices = notices;
    this.benefits = benefits;
    this.clock = clock;
  }

  /** 저장. 이미 저장했으면 그대로예요. 저장한 대상 ID를 돌려줘요 (합쳐진 공고면 남은 공고 ID) */
  @Transactional
  public UUID add(UUID userId, String targetType, UUID targetId) {
    String type = targetType(targetType);
    UUID resolved = resolve(type, targetId);
    favorites.lockUser(userId); // 같은 회원의 저장은 하나씩: 개수 확인과 넣기 사이에 다른 요청이 끼지 않게
    if (favorites.exists(userId, type, sameTarget(type, targetId, resolved))) {
      return resolved; // 다시 저장해도 그대로 (처음 저장한 시각 유지)
    }
    if (favorites.count(userId) >= MAX_FAVORITES) {
      throw new CustomException(ErrorCode.FAVORITE_LIMIT_EXCEEDED);
    }
    favorites.add(userId, type, resolved, clock.instant());
    return resolved;
  }

  /** 지우기. 없어도 조용히 끝나요. 공고는 합치기 전 ID로 저장한 줄도 함께 지워요 */
  @Transactional
  public void remove(UUID userId, String targetType, UUID targetId) {
    String type = targetType(targetType);
    UUID resolved =
        "NOTICE".equals(type)
            ? notices.findSummary(targetId).map(NoticeSummary::noticeId).orElse(targetId)
            : targetId;
    favorites.remove(userId, type, sameTarget(type, targetId, resolved));
  }

  /**
   * 같은 대상으로 볼 ID들. 공고는 요청 ID·남은 공고 ID·거기 합쳐진 공고 ID: 합치기 전에 저장한 줄은 합쳐진 공고 ID에 남아 있어(알림은 그 줄도 봐요), 남은
   * 공고로 지우면 그 줄이 남아 알림이 계속 가고, 다시 저장하면 두 줄이 됐어요(2026-11-10 재검토).
   */
  private List<UUID> sameTarget(String type, UUID requested, UUID resolved) {
    Set<UUID> ids = new LinkedHashSet<>(List.of(requested, resolved));
    if ("NOTICE".equals(type)) {
      ids.addAll(notices.mergedFrom(resolved));
    }
    return List.copyOf(ids);
  }

  /** 최근 저장한 것부터. {@code targetType}이 비면 모두 */
  @Transactional(readOnly = true)
  public CursorPageResponse<FavoriteResponse> list(
      UUID userId, String targetType, String cursor, Integer size) {
    String type = targetType == null || targetType.isBlank() ? null : targetType(targetType);
    String sort = SORT + (type == null ? "" : ":" + type); // 거르는 종류가 바뀌면 처음부터
    CursorQuery query = CursorQuery.of(cursor, size, sort);
    Instant afterAt = null;
    UUID afterId = null;
    if (query.after() != null) {
      try {
        afterAt = Instant.parse(query.after().value());
      } catch (RuntimeException e) {
        throw new CustomException(ErrorCode.INVALID_CURSOR, ErrorCode.INVALID_CURSOR.message());
      }
      afterId = query.after().id();
    }
    List<Favorite> rows = favorites.page(userId, type, afterAt, afterId, query.fetchSize());
    // 종류마다 한 번에 읽어요 (한 줄씩 물으면 페이지마다 최대 20번)
    Map<UUID, NoticeSummary> noticeSummaries = notices.findSummaries(ids(rows, "NOTICE"));
    Map<UUID, BenefitSummary> benefitSummaries = benefits.findSummaries(ids(rows, "BENEFIT"));
    Map<UUID, PolicySummary> policySummaries =
        notices.findPolicySummaries(
            rows.stream()
                .filter(f -> !"NOTICE".equals(f.targetType()) && !"BENEFIT".equals(f.targetType()))
                .map(Favorite::targetId)
                .toList());
    return CursorPageResponse.from(
        rows,
        query.size(),
        f -> response(f, noticeSummaries, benefitSummaries, policySummaries),
        f -> CursorKey.of(sort, f.createdAt(), f.targetId()));
  }

  private static List<UUID> ids(List<Favorite> rows, String type) {
    return rows.stream().filter(f -> type.equals(f.targetType())).map(Favorite::targetId).toList();
  }

  /** 목록 한 줄: 대상의 제목·기관·상태·신청 기간을 그 모듈 조회 결과로 채워요. 대상이 사라졌으면 제목 없이 */
  private FavoriteResponse response(
      Favorite f,
      Map<UUID, NoticeSummary> noticeSummaries,
      Map<UUID, BenefitSummary> benefitSummaries,
      Map<UUID, PolicySummary> policySummaries) {
    UUID id = f.targetId();
    return switch (f.targetType()) {
      case "NOTICE" -> {
        NoticeSummary n = noticeSummaries.get(id);
        yield n == null
            ? empty(f, ScreenPaths.of("NOTICE", id))
            : new FavoriteResponse(
                f.targetType(),
                id,
                f.createdAt(),
                n.title(),
                n.provider(),
                n.status(),
                n.applyStart(),
                n.applyEnd(),
                ScreenPaths.notice(id, n.field()));
      }
      case "BENEFIT" ->
          java.util.Optional.ofNullable(benefitSummaries.get(id))
              .map(
                  b ->
                      new FavoriteResponse(
                          f.targetType(),
                          id,
                          f.createdAt(),
                          b.title(),
                          b.agency(),
                          b.status(),
                          b.applyStart(),
                          b.applyEnd(),
                          ScreenPaths.of("BENEFIT", id)))
              .orElseGet(() -> empty(f, ScreenPaths.of("BENEFIT", id)));
      default ->
          java.util.Optional.ofNullable(policySummaries.get(id))
              .map(
                  p ->
                      new FavoriteResponse(
                          f.targetType(),
                          id,
                          f.createdAt(),
                          p.title(),
                          p.organization(),
                          p.status(),
                          p.applyStart(),
                          p.applyEnd(),
                          ScreenPaths.of(f.targetType(), id)))
              .orElseGet(() -> empty(f, ScreenPaths.of(f.targetType(), id)));
    };
  }

  private static FavoriteResponse empty(Favorite f, String linkPath) {
    return new FavoriteResponse(
        f.targetType(), f.targetId(), f.createdAt(), null, null, null, null, null, linkPath);
  }

  private UUID resolve(String type, UUID id) {
    return switch (type) {
      case "NOTICE" ->
          notices
              .findSummary(id)
              .map(NoticeSummary::noticeId)
              .orElseThrow(FavoriteService::notFound);
      case "BENEFIT" -> {
        BenefitSummary b = benefits.findSummary(id).orElseThrow(FavoriteService::notFound);
        if ("HIDDEN".equals(b.status())) {
          throw notFound();
        }
        yield b.benefitId();
      }
      // 창업지원 사업·사업공간 모집은 notice.policy_judgments에 있어요 (정책 ID = rawPolicyId)
      case "STARTUP_SUPPORT", "SPACE_RECRUITMENT" ->
          notices
              .findPolicySummary(id)
              .filter(p -> p.field().equals(type))
              .map(PolicySummary::policyId)
              .orElseThrow(FavoriteService::notFound);
      default -> throw notFound();
    };
  }

  /** NOTICE · BENEFIT · STARTUP_SUPPORT · SPACE_RECRUITMENT (대소문자 상관없이) */
  static String targetType(String value) {
    String type = value == null ? "" : value.strip().toUpperCase(Locale.ROOT).replace('-', '_');
    return switch (type) {
      case "NOTICE", "BENEFIT", "STARTUP_SUPPORT", "SPACE_RECRUITMENT" -> type;
      default ->
          throw new CustomException(
              ErrorCode.VALIDATION_FAILED,
              "targetType: NOTICE·BENEFIT·STARTUP_SUPPORT·SPACE_RECRUITMENT 중 하나예요");
    };
  }

  private static CustomException notFound() {
    return new CustomException(ErrorCode.FAVORITE_TARGET_NOT_FOUND);
  }
}
