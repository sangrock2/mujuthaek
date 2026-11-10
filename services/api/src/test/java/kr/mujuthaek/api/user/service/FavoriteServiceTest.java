package kr.mujuthaek.api.user.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import kr.mujuthaek.api.benefit.service.BenefitQueryService;
import kr.mujuthaek.api.benefit.service.BenefitSummary;
import kr.mujuthaek.api.common.exception.CustomException;
import kr.mujuthaek.api.common.exception.ErrorCode;
import kr.mujuthaek.api.notice.service.NoticeQueryService;
import kr.mujuthaek.api.notice.service.NoticeSummary;
import kr.mujuthaek.api.notice.service.PolicySummary;
import kr.mujuthaek.api.user.repository.FavoriteRepository;
import org.junit.jupiter.api.Test;

/** 관심 공고 저장: 합쳐진 공고, 숨긴 혜택, 창업지원 사업·사업공간 모집(notice 정책), 200개 상한 (DB 없이). */
class FavoriteServiceTest {

  final FavoriteRepository repository = mock(FavoriteRepository.class);
  final NoticeQueryService notices = mock(NoticeQueryService.class);
  final BenefitQueryService benefits = mock(BenefitQueryService.class);
  final FavoriteService service =
      new FavoriteService(
          repository,
          notices,
          benefits,
          Clock.fixed(Instant.parse("2026-10-26T00:00:00Z"), ZoneOffset.UTC));
  final UUID user = UUID.randomUUID();

  @Test
  void mergedNoticeIsSavedAsTheRemainingOne() {
    UUID asked = UUID.randomUUID();
    UUID remaining = UUID.randomUUID();
    when(notices.findSummary(asked)).thenReturn(Optional.of(notice(remaining)));

    assertThat(service.add(user, "notice", asked)).isEqualTo(remaining);
    verify(repository).add(eq(user), eq("NOTICE"), eq(remaining), any());
  }

  @Test
  void aNoticeSavedBeforeItWasMergedIsRemovedWithItAndNotSavedTwice() {
    // 2026-11-10 재검토: 합치기 전에 저장한 줄(합쳐진 공고 ID)은 알림이 보는데, 남은 공고로 지우면 그 줄이 남아 알림이 계속 갔음
    UUID merged = UUID.randomUUID();
    UUID remaining = UUID.randomUUID();
    when(notices.findSummary(any())).thenReturn(Optional.of(notice(remaining)));
    when(notices.mergedFrom(remaining)).thenReturn(List.of(merged));
    when(repository.exists(eq(user), eq("NOTICE"), any()))
        .thenAnswer(i -> i.<java.util.Collection<?>>getArgument(2).contains(merged));

    assertThat(service.add(user, "NOTICE", remaining)).isEqualTo(remaining);
    verify(repository, never()).add(any(), anyString(), any(), any());
    service.remove(user, "NOTICE", remaining);
    verify(repository).remove(user, "NOTICE", List.of(remaining, merged));
  }

  @Test
  void hiddenBenefitIsNotFound() {
    UUID hidden = UUID.randomUUID();
    UUID open = UUID.randomUUID();
    when(benefits.findSummary(hidden))
        .thenReturn(Optional.of(benefit(hidden, "BENEFIT", "HIDDEN")));
    when(benefits.findSummary(open)).thenReturn(Optional.of(benefit(open, "BENEFIT", "OPEN")));

    assertThatThrownBy(() -> service.add(user, "BENEFIT", hidden)).satisfies(e -> notFound(e));
    assertThat(service.add(user, "BENEFIT", open)).isEqualTo(open);
  }

  @Test
  void startupSupportAndSpaceRecruitmentAreNoticePolicies() {
    // 창업지원 사업·사업공간 모집은 benefit이 아니라 notice.policy_judgments에 있어요 (정책 ID = rawPolicyId)
    UUID startup = UUID.randomUUID();
    UUID space = UUID.randomUUID();
    when(notices.findPolicySummary(startup))
        .thenReturn(Optional.of(policy(startup, "STARTUP_SUPPORT")));
    when(notices.findPolicySummary(space))
        .thenReturn(Optional.of(policy(space, "SPACE_RECRUITMENT")));

    assertThat(service.add(user, "startup-support", startup)).isEqualTo(startup);
    assertThat(service.add(user, "space-recruitment", space)).isEqualTo(space);
    verify(repository).add(eq(user), eq("STARTUP_SUPPORT"), eq(startup), any());
    verify(repository).add(eq(user), eq("SPACE_RECRUITMENT"), eq(space), any());
    assertThatThrownBy(() -> service.add(user, "SPACE_RECRUITMENT", startup))
        .as("종류가 다르면 없는 것")
        .satisfies(e -> notFound(e));
    assertThatThrownBy(() -> service.add(user, "STARTUP_SUPPORT", UUID.randomUUID()))
        .satisfies(e -> notFound(e));
    verify(benefits, never()).findSummary(any());
  }

  @Test
  void limitStopsNewOnesButNotSavingAgain() {
    UUID id = UUID.randomUUID();
    when(notices.findSummary(any())).thenAnswer(i -> Optional.of(notice(i.getArgument(0))));
    when(repository.count(user)).thenReturn((long) FavoriteService.MAX_FAVORITES);
    when(repository.exists(user, "NOTICE", List.of(id))).thenReturn(true);

    assertThat(service.add(user, "NOTICE", id)).isEqualTo(id); // 이미 있는 것은 그대로
    assertThatThrownBy(() -> service.add(user, "NOTICE", UUID.randomUUID()))
        .isInstanceOfSatisfying(
            CustomException.class,
            e -> assertThat(e.errorCode()).isEqualTo(ErrorCode.FAVORITE_LIMIT_EXCEEDED));
    verify(repository, never()).add(any(), anyString(), any(), any());
  }

  @Test
  void listFillsTitleStatusDeadlineAndScreenPerKind() {
    UUID house = UUID.randomUUID();
    UUID spaceNotice = UUID.randomUUID();
    UUID benefit = UUID.randomUUID();
    UUID startup = UUID.randomUUID();
    UUID gone = UUID.randomUUID();
    Instant at = Instant.parse("2026-10-20T00:00:00Z");
    when(repository.page(eq(user), any(), any(), any(), org.mockito.ArgumentMatchers.anyInt()))
        .thenReturn(
            List.of(
                new FavoriteRepository.Favorite("NOTICE", house, at),
                new FavoriteRepository.Favorite("NOTICE", spaceNotice, at),
                new FavoriteRepository.Favorite("BENEFIT", benefit, at),
                new FavoriteRepository.Favorite("STARTUP_SUPPORT", startup, at),
                new FavoriteRepository.Favorite("NOTICE", gone, at)));
    var end = java.time.LocalDate.parse("2026-11-03");
    when(notices.findSummaries(any()))
        .thenReturn(
            java.util.Map.of(
                house,
                new NoticeSummary(
                    house,
                    1,
                    "HOUSING",
                    "행복주택",
                    "LH",
                    null,
                    "APPLYING",
                    null,
                    end,
                    List.of(),
                    false,
                    "/",
                    null),
                spaceNotice,
                new NoticeSummary(
                    spaceNotice,
                    1,
                    "BUSINESS_SPACE",
                    "창업센터",
                    "SH",
                    null,
                    "APPLYING",
                    null,
                    end,
                    List.of(),
                    false,
                    "/",
                    null)));
    when(benefits.findSummaries(List.of(benefit)))
        .thenReturn(
            java.util.Map.of(
                benefit,
                new BenefitSummary(
                    benefit,
                    "BENEFIT",
                    1,
                    "청년 월세",
                    "서울시",
                    "OPEN",
                    null,
                    end,
                    false,
                    "NATIONWIDE",
                    List.of(),
                    null)));
    when(notices.findPolicySummaries(List.of(startup)))
        .thenReturn(
            java.util.Map.of(
                startup,
                new PolicySummary(
                    startup,
                    1,
                    "STARTUP_SUPPORT",
                    "창업 지원금",
                    "중기부",
                    "APPLYING",
                    null,
                    end,
                    List.of(),
                    null)));

    var items = service.list(user, null, null, null).items();

    assertThat(items)
        .extracting(
            f -> f.title() + "|" + f.organization() + "|" + f.applyEnd() + "|" + f.linkPath())
        .containsExactly(
            "행복주택|LH|2026-11-03|/notices/" + house,
            "창업센터|SH|2026-11-03|/business/spaces/" + spaceNotice,
            "청년 월세|서울시|2026-11-03|/benefits/" + benefit,
            "창업 지원금|중기부|2026-11-03|/business/support/" + startup,
            "null|null|null|/notices/" + gone); // 사라진 공고는 제목 없이
    // 종류마다 한 번에 읽어요 (한 줄씩 묻지 않아요)
    verify(benefits, never()).findSummary(any());
    verify(notices, never()).findPolicySummary(any());
  }

  private static void notFound(Throwable e) {
    assertThat(((CustomException) e).errorCode()).isEqualTo(ErrorCode.FAVORITE_TARGET_NOT_FOUND);
  }

  private static NoticeSummary notice(UUID id) {
    return new NoticeSummary(
        id, 1, "HOUSING", "t", null, null, "APPLYING", null, null, List.of(), false, "/", null);
  }

  private static PolicySummary policy(UUID id, String field) {
    return new PolicySummary(id, 2, field, "t", null, "APPLYING", null, null, List.of(), null);
  }

  private static BenefitSummary benefit(UUID id, String field, String status) {
    return new BenefitSummary(
        id, field, 1, "t", null, status, null, null, false, "NATIONWIDE", List.of(), null);
  }
}
