package kr.mujuthaek.api.user.service;

import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.*;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import kr.mujuthaek.api.common.exception.CustomException;
import kr.mujuthaek.api.user.repository.AdminUserRepository;
import org.junit.jupiter.api.Test;

class AdminTransferRecentAuthenticationTest {
  @Test
  void oldMissingAndFutureSessionAuthenticationCannotBorrowAnotherDevicesRecentLogin() {
    Instant now = Instant.parse("2026-11-16T03:00:00Z");
    UUID actor = UUID.randomUUID();
    UUID target = UUID.randomUUID();
    var users = mock(AdminUserRepository.class);
    when(users.access(actor, now))
        .thenReturn(
            Optional.of(new AdminUserRepository.Access("SUPER_ADMIN", Set.of(), false, false)));
    var service = new AdminUserService(users, Clock.fixed(now, ZoneOffset.UTC));
    for (Instant authenticatedAt :
        new Instant[] {null, Instant.EPOCH, now.minusSeconds(601), now.plusSeconds(1)}) {
      assertThatThrownBy(() -> service.transfer(target, actor, authenticatedAt))
          .isInstanceOf(CustomException.class)
          .hasMessageContaining("10분");
    }
    verify(users, never()).find(any(), any());
    verify(users, never()).setRole(any(), any(), any());
  }
}
