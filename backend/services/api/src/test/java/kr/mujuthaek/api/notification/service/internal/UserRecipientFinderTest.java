package kr.mujuthaek.api.notification.service.internal;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.util.List;
import java.util.Map;
import java.util.UUID;
import kr.mujuthaek.api.notice.service.NoticeQueryService;
import kr.mujuthaek.api.user.service.UserNotificationQueryService;
import org.junit.jupiter.api.Test;

/** 관심 알림 대상: 공고는 그 공고에 합쳐진 공고의 관심 회원까지. */
class UserRecipientFinderTest {

  private final UserNotificationQueryService users = mock(UserNotificationQueryService.class);
  private final NoticeQueryService notices = mock(NoticeQueryService.class);
  private final UserRecipientFinder finder =
      new UserRecipientFinder(
          users,
          notices,
          new UserRecipientFinder.Properties(List.of()),
          mock(kr.mujuthaek.api.user.service.EmailNotificationService.class));

  @Test
  void favoritesOfNoticesMergedIntoTheNoticeAreRecipientsToo() {
    // 2026-11-10 코드 검토: 관심은 합쳐진 공고 ID에 그대로 남는데 남은 공고 ID로만 찾아, 그 회원들이 마감·정정·후속 알림을 못 받았음
    UUID kept = UUID.randomUUID();
    UUID merged = UUID.randomUUID();
    UUID both = UUID.randomUUID();
    UUID onlyMerged = UUID.randomUUID();
    when(users.favoriteAudience("NOTICE", kept)).thenReturn(List.of(both));
    when(users.favoriteAudience("NOTICE", merged)).thenReturn(List.of(both, onlyMerged));
    when(notices.mergedFrom(kept)).thenReturn(List.of(merged));
    when(users.preferences(any())).thenReturn(Map.of());

    assertThat(finder.forFavorite("NOTICE", kept, "DEADLINE_D3"))
        .extracting(Recipient::userId)
        .containsExactly(both, onlyMerged); // 두 공고 모두 관심인 회원은 한 번

    UUID policy = UUID.randomUUID();
    finder.forFavorite("STARTUP_SUPPORT", policy, "CORRECTED");
    verify(notices, never()).mergedFrom(policy); // 공고가 아니면 합치기가 없어요
  }
}
