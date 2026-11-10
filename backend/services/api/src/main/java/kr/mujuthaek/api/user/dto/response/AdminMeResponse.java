package kr.mujuthaek.api.user.dto.response;

import java.time.OffsetDateTime;
import java.util.List;
import java.util.UUID;

/**
 * 관리자 화면을 여는 회원의 지금 권한 (화면이 메뉴·버튼을 고르는 데 써요. 실제 확인은 서버가 요청마다 다시 해요).
 *
 * @param role ADMIN 또는 SUPER_ADMIN
 * @param permissions 쓸 수 있는 권한 (최상위는 전부)
 * @param active 지금 관리자 화면을 쓸 수 있는지 (긴급 정지·이용 정지면 false)
 * @param freeze 관리자 긴급 정지 중이면 그 내용
 */
public record AdminMeResponse(
    UUID id,
    String nickname,
    String role,
    List<String> permissions,
    boolean active,
    Freeze freeze) {

  public record Freeze(String reason, OffsetDateTime at) {}
}
