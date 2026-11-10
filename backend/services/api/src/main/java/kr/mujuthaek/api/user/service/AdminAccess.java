package kr.mujuthaek.api.user.service;

import java.util.EnumSet;
import java.util.Set;
import java.util.UUID;
import kr.mujuthaek.api.user.domain.AdminPermission;
import kr.mujuthaek.api.user.domain.Role;

/**
 * 관리자 화면을 쓰는 회원의 지금 상태 (요청마다 DB에서 읽어요. 토큰의 권한은 쓰지 않아요).
 *
 * @param permissions 받은 권한. 최상위는 줄이 없어도 모두 가진 것으로 봐요({@link #effective()})
 * @param suspended 이용 정지 중
 * @param frozen 관리자 긴급 정지 중 (최상위는 영향 없음)
 */
public record AdminAccess(
    UUID userId, Role role, Set<AdminPermission> permissions, boolean suspended, boolean frozen) {

  public boolean isSuper() {
    return role == Role.SUPER_ADMIN;
  }

  /** 지금 관리자 화면을 쓸 수 있는지: 관리자이고, 이용 정지가 아니고, 긴급 정지 중이면 최상위만. */
  public boolean active() {
    return role.isAdmin() && !suspended && (!frozen || isSuper());
  }

  /** 실제로 가진 권한 (최상위는 전부). */
  public Set<AdminPermission> effective() {
    return isSuper()
        ? EnumSet.allOf(AdminPermission.class)
        : permissions.isEmpty()
            ? EnumSet.noneOf(AdminPermission.class)
            : EnumSet.copyOf(permissions);
  }

  public boolean has(AdminPermission permission) {
    return active() && effective().contains(permission);
  }

  /** 그 권한들을 내가 모두 가졌는지 (가진 권한만 주고 뺄 수 있어요). */
  public boolean covers(Set<AdminPermission> others) {
    return effective().containsAll(others);
  }
}
