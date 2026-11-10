package kr.mujuthaek.api.user.domain;

/**
 * 회원 권한. 처음 로그인하면 USER. ADMIN(일반 관리자)은 관리자 화면에서 「관리자 지정」 권한을 가진 관리자가 정하고, SUPER_ADMIN(최상위 관리자, 1명)은
 * DB로 정하거나 최상위가 넘겨요. 관리자 화면에서 무엇을 할 수 있는지는 {@link AdminPermission}으로 따로 받아요.
 */
public enum Role {
  USER,
  ADMIN,
  SUPER_ADMIN;

  /** 스프링 시큐리티 권한 이름 (hasRole("ADMIN")이 ROLE_ADMIN을 봐요). */
  public String authority() {
    return "ROLE_" + name();
  }

  /** 일반 관리자 또는 최상위 관리자. */
  public boolean isAdmin() {
    return this != USER;
  }
}
