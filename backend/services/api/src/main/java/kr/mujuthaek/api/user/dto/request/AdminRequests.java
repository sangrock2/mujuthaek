package kr.mujuthaek.api.user.dto.request;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.time.Instant;
import java.util.Set;
import java.util.UUID;
import kr.mujuthaek.api.user.domain.AdminPermission;

/** 관리자 회원 관리 요청 본문. */
public final class AdminRequests {

  private AdminRequests() {}

  /** 일반 관리자의 권한을 이 목록으로 맞춰요 (빠진 권한은 빼고, 새 권한은 줘요). */
  public record Permissions(@NotNull Set<AdminPermission> permissions) {}

  /**
   * 이용 정지.
   *
   * @param until 비우면 해제할 때까지
   */
  public record Suspend(@NotBlank @Size(max = 200) String reason, Instant until) {}

  /** 관리자 긴급 정지. */
  public record Freeze(@Size(max = 200) String reason) {}

  /** 최상위 관리자 넘기기. */
  public record Transfer(@NotNull UUID userId) {}
}
