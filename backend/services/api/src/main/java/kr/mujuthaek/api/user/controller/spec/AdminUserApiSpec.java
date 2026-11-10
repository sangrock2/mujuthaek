package kr.mujuthaek.api.user.controller.spec;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.util.List;
import java.util.UUID;
import kr.mujuthaek.api.user.dto.request.AdminRequests;
import kr.mujuthaek.api.user.dto.request.RoleChangeRequest;
import kr.mujuthaek.api.user.dto.response.AdminMeResponse;
import kr.mujuthaek.api.user.dto.response.AdminUserResponse;
import kr.mujuthaek.api.user.service.LoginUser;

@Tag(
    name = "관리자 회원 관리",
    description =
        "회원 찾기, 관리자 지정·해제, 권한 주고 빼기, 이용 정지, 최상위 넘기기·긴급 정지예요. 관리자만 부를 수 있고 필요한 권한은 API마다 달라요. "
            + "권한은 요청마다 DB의 지금 상태로 봐서, 이용 정지 중이거나 긴급 정지 중(최상위 제외)이면 「내 관리자 권한」 말고는 막혀요.")
public interface AdminUserApiSpec {

  @Operation(
      summary = "내 관리자 권한",
      description =
          "관리자 화면이 메뉴·버튼을 고르는 데 써요(실제 확인은 서버가 요청마다 다시 해요). 관리자(ADMIN·SUPER_ADMIN)면 이용 정지·긴급 정지 중이어도 부를 수 있어요. "
              + "이용 정지 중이거나 긴급 정지 중(최상위 제외)이면 active가 false이고 permissions가 비어요. 최상위는 permissions에 모든 권한이 와요. "
              + "긴급 정지 중이면 freeze에 이유와 시각이 와요.")
  AdminMeResponse me(@Parameter(hidden = true) LoginUser admin);

  @Operation(
      summary = "회원 찾기",
      description =
          "가입한 지 최근 순으로 한 쪽에 30명씩 줘요. total은 조건에 맞는 전체 수예요. 소셜 계정 원본 정보(이메일 등)는 주지 않아요. "
              + "권한 USERS_VIEW·ADMIN_APPOINT·PERMISSION_GRANT·PERMISSION_REVOKE·USERS_SUSPEND 중 하나.")
  AdminUserResponse.Page list(
      @Parameter(description = "닉네임 일부 또는 회원 ID 전체. 비우면 모두") String query,
      @Parameter(
              description = "USER(일반 회원)·ADMIN(일반·최상위 관리자)·SUSPENDED(지금 이용 정지 중). 비우거나 다른 값이면 모두")
          String filter,
      @Parameter(description = "쪽 번호 (0부터, 기본 0). 0보다 작으면 0으로 봐요", example = "0") int page);

  @Operation(
      summary = "회원 이름만",
      description =
          "처리 기록에서 관리자 이름을 찾을 때 써요. ID·닉네임·단계(role)만 줘요. 겹친 ID는 하나로 보고 앞에서 100명까지만 찾아요. 없는 ID는 빠져요. "
              + "지금 관리자 화면을 쓸 수 있는 관리자 누구나.")
  @ApiResponse(responseCode = "200", description = "찾은 회원 이름")
  @ApiResponse(responseCode = "400", description = "VALIDATION_FAILED — ids가 없거나 UUID가 아닌 값이 있어요")
  List<AdminUserResponse.Name> names(@Parameter(description = "찾을 회원 ID (쉼표로 이어요)") List<UUID> ids);

  @Operation(
      summary = "관리자 지정·해제",
      description =
          "role이 ADMIN이면 일반 관리자로 지정하고, USER면 해제해요. 지금과 같으면 바꾸지 않고 그대로 줘요. 권한 ADMIN_APPOINT(「관리자 지정」). "
              + "해제하면 받은 권한을 모두 빼고 그 회원의 로그인을 바로 끊어요. 「권한 부여」·「권한 박탈」을 가진 관리자는 최상위만 해제할 수 있고, "
              + "그 밖에는 그 관리자의 권한을 내가 모두 가졌을 때만 해제할 수 있어요. 최상위 관리자는 바꿀 수 없어요(어기면 403). 바꾼 것은 변경 기록에 남아요.")
  @ApiResponse(responseCode = "200", description = "바뀐 회원")
  @ApiResponse(responseCode = "400", description = "VALIDATION_FAILED — role이 USER·ADMIN이 아니에요")
  @ApiResponse(responseCode = "404", description = "NOT_FOUND — 없는 회원이에요")
  @ApiResponse(
      responseCode = "409",
      description = "CONFLICT — 내 단계는 바꿀 수 없어요. 이용 정지 중인 회원은 관리자로 지정할 수 없어요")
  AdminUserResponse changeRole(
      @Parameter(description = "회원 ID") UUID id,
      RoleChangeRequest request,
      @Parameter(hidden = true) LoginUser admin);

  @Operation(
      summary = "관리자 권한 맞추기",
      description =
          "일반 관리자의 권한을 permissions 목록으로 맞춰요: 목록에 없는 권한은 빼고 새 권한은 줘요. 바뀌는 게 없으면 그대로 줘요. "
              + "권한 PERMISSION_GRANT·PERMISSION_REVOKE 중 하나. 주려면 「권한 부여」, 빼려면 「권한 박탈」이 있어야 하고, 내가 가진 권한만 주고 뺄 수 있어요. "
              + "「권한 부여」·「권한 박탈」 자체를 주고 빼거나, 그 권한을 가진 관리자의 권한을 바꾸는 일은 최상위만 해요. "
              + "최상위 관리자는 바꿀 수 없어요(어기면 403). 바꾼 것은 변경 기록에 남아요.")
  @ApiResponse(responseCode = "200", description = "바뀐 회원")
  @ApiResponse(
      responseCode = "400",
      description = "VALIDATION_FAILED — permissions가 없거나 모르는 권한 이름이 있어요")
  @ApiResponse(responseCode = "404", description = "NOT_FOUND — 없는 회원이에요")
  @ApiResponse(
      responseCode = "409",
      description = "CONFLICT — 내 권한은 바꿀 수 없어요. 일반 회원이라 먼저 관리자로 지정해야 해요")
  AdminUserResponse permissions(
      @Parameter(description = "회원 ID") UUID id,
      AdminRequests.Permissions request,
      @Parameter(hidden = true) LoginUser admin);

  @Operation(
      summary = "이용 정지",
      description =
          "회원을 이용 정지해요. 이미 정지 중이면 이유·기간을 바꿔요. reason은 꼭 넣고(200자까지), until을 비우면 해제할 때까지예요. "
              + "정지하면 그 회원의 로그인을 바로 끊어요. 권한 USERS_SUSPEND(「이용 정지」). 관리자를 정지하려면 그 관리자의 권한을 내가 모두 가져야 하고, "
              + "「권한 부여」·「권한 박탈」을 가진 관리자는 최상위만 정지할 수 있어요. 최상위 관리자는 정지할 수 없어요(어기면 403). 바꾼 것은 변경 기록에 남아요.")
  @ApiResponse(responseCode = "200", description = "정지한 회원")
  @ApiResponse(
      responseCode = "400",
      description = "VALIDATION_FAILED — reason이 비었거나 200자를 넘어요. until이 지금보다 뒤가 아니에요")
  @ApiResponse(responseCode = "404", description = "NOT_FOUND — 없는 회원이에요")
  @ApiResponse(responseCode = "409", description = "CONFLICT — 나 자신은 정지할 수 없어요")
  AdminUserResponse suspend(
      @Parameter(description = "회원 ID") UUID id,
      AdminRequests.Suspend request,
      @Parameter(hidden = true) LoginUser admin);

  @Operation(
      summary = "이용 정지 해제",
      description =
          "이용 정지를 풀어요. 정지 중이 아니어도 200이에요. 권한 USERS_SUSPEND(「이용 정지」). "
              + "관리자의 정지를 풀 때도 정지할 때처럼 그 관리자의 권한을 내가 모두 가져야 하고, 「권한 부여」·「권한 박탈」을 가진 관리자는 최상위만 풀 수 있어요(어기면 403).")
  @ApiResponse(responseCode = "200", description = "정지를 푼 회원")
  @ApiResponse(responseCode = "404", description = "NOT_FOUND — 없는 회원이에요")
  @ApiResponse(responseCode = "409", description = "CONFLICT — 내 정지는 풀 수 없어요")
  AdminUserResponse unsuspend(
      @Parameter(description = "회원 ID") UUID id, @Parameter(hidden = true) LoginUser admin);

  @Operation(
      summary = "관리자 변경 기록",
      description =
          "관리자 지정·해제, 권한 주기·빼기, 이용 정지·해제, 최상위 넘기기, 긴급 정지·풀기 기록을 최근 것부터 300줄까지 줘요. "
              + "권한 ACTIVITY·ADMIN_APPOINT·PERMISSION_GRANT·PERMISSION_REVOKE·USERS_SUSPEND 중 하나.")
  List<AdminUserResponse.Change> changes(
      @Parameter(description = "최근 며칠 (기본 30, 1~90 밖이면 가까운 끝값으로 맞춰요)", example = "30") int days);

  @Operation(
      summary = "최상위 관리자 넘기기",
      description =
          "최상위 관리자만. userId의 일반 관리자를 최상위로 바꾸고, 넘긴 나는 모든 권한을 가진 일반 관리자가 돼요(새 최상위가 나중에 조정해요). "
              + "로그인한 지 10분 안에만 넘길 수 있어요(지났으면 403이라 다시 로그인해야 해요). 응답은 새 최상위 관리자예요.")
  @ApiResponse(responseCode = "200", description = "새 최상위 관리자")
  @ApiResponse(responseCode = "400", description = "VALIDATION_FAILED — userId가 없어요")
  @ApiResponse(responseCode = "404", description = "NOT_FOUND — 없는 회원이에요")
  @ApiResponse(
      responseCode = "409",
      description =
          "CONFLICT — 나 자신에게는 넘길 수 없어요. 일반 관리자가 아니라 먼저 관리자로 지정해야 해요. 이용 정지 중인 관리자에게는 넘길 수 없어요")
  AdminUserResponse transfer(
      AdminRequests.Transfer request, @Parameter(hidden = true) LoginUser admin);

  @Operation(
      summary = "관리자 긴급 정지",
      description =
          "최상위 관리자만. 최상위를 뺀 모든 관리자의 관리자 화면을 멈춰요. 본문은 비워도 되고 reason은 200자까지예요. "
              + "이미 정지 중이면 그대로 둬요. 응답은 내 관리자 권한(freeze에 정지 내용)이에요.")
  @ApiResponse(responseCode = "200", description = "내 관리자 권한")
  @ApiResponse(responseCode = "400", description = "VALIDATION_FAILED — reason이 200자를 넘어요")
  AdminMeResponse freeze(AdminRequests.Freeze request, @Parameter(hidden = true) LoginUser admin);

  @Operation(
      summary = "관리자 긴급 정지 풀기",
      description = "최상위 관리자만. 긴급 정지 중이 아니어도 그대로 200이에요. 응답은 내 관리자 권한이에요.")
  AdminMeResponse unfreeze(@Parameter(hidden = true) LoginUser admin);
}
