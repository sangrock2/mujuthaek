package kr.mujuthaek.api.user.dto.response;

import java.time.Instant;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.UUID;

/**
 * 관리자 회원 관리의 회원 한 명. 소셜 계정 원본 정보(이메일 등)는 주지 않아요.
 *
 * @param role USER, ADMIN(일반 관리자) 또는 SUPER_ADMIN(최상위 관리자)
 * @param providers 이어진 소셜 로그인 (KAKAO, NAVER, GOOGLE)
 * @param permissions 일반 관리자가 받은 권한 (최상위는 전부라 비워 둬요)
 * @param suspension 지금 이용 정지 중이면 그 내용, 아니면 null
 */
public record AdminUserResponse(
    UUID id,
    String nickname,
    String role,
    List<String> providers,
    OffsetDateTime joinedAt,
    OffsetDateTime lastLoginAt,
    List<String> permissions,
    Suspension suspension) {

  /**
   * @param until 비어 있으면 해제할 때까지
   */
  public record Suspension(String reason, OffsetDateTime until, OffsetDateTime at) {}

  /** 회원 목록 한 쪽. total은 조건에 맞는 전체 수 */
  public record Page(List<AdminUserResponse> items, long total) {}

  /** 이름만 (처리 기록의 관리자 이름 찾기). */
  public record Name(UUID id, String nickname, String role) {}

  /**
   * 관리자 변경 기록 한 줄.
   *
   * @param kind APPOINT(관리자 지정)·DISMISS(해제)·GRANT(권한 주기)·REVOKE(권한 빼기)·SUSPEND(이용 정지)·UNSUSPEND(정지
   *     해제)·TRANSFER(최상위 넘기기)·FREEZE(긴급 정지)·UNFREEZE(긴급 정지 풀기)
   * @param permission GRANT·REVOKE의 권한
   * @param userId 대상 회원 (긴급 정지는 null)
   * @param changedBy 바꾼 관리자 (탈퇴했으면 null)
   */
  public record Change(
      long id,
      Instant changedAt,
      String kind,
      String permission,
      String note,
      UUID userId,
      String nickname,
      UUID changedBy,
      String changedByNickname) {}
}
