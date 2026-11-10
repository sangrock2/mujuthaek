package kr.mujuthaek.api.user.controller.spec;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.tags.Tag;
import kr.mujuthaek.api.user.dto.request.ContactEmailRequest;
import kr.mujuthaek.api.user.dto.response.MeResponse;
import kr.mujuthaek.api.user.dto.response.MyReportsResponse;
import kr.mujuthaek.api.user.dto.response.WithdrawalResponse;
import kr.mujuthaek.api.user.service.LoginUser;
import org.springframework.http.ResponseEntity;

@Tag(name = "내 계정", description = "내 정보·내 제보·연락용 이메일·탈퇴예요. 로그인한 회원만 부를 수 있어요.")
public interface UserApiSpec {

  @Operation(
      summary = "탈퇴 시작",
      description =
          "바로 지우지 않고, 본인 확인과 소셜 연결 끊기를 위해 그 소셜로 다시 로그인하는 주소(reauthUrl)를 줘요. 프론트가 그 주소로 페이지를"
              + " 이동하면(fetch가 아니라 주소 이동) 다시 로그인 → 회원 삭제(hard delete) → 소셜 연결 끊기 →"
              + " FRONTEND_URL/withdrawn으로 돌아가요. 실패하거나 취소하면"
              + " FRONTEND_URL/mypage?withdraw=expired|account_mismatch|cancelled|failed로 돌아가요. 주소의"
              + " 일회용 티켓은 expiresIn초(10분) 동안만 쓸 수 있고, 다시 부르면 이전 티켓은 없어져요. otherProviders(함께 연결된 다른"
              + " 소셜)는 서버가 연결을 끊을 수 없어서 각 서비스에서 직접 해제하라고 보여 줘요.")
  @ApiResponse(responseCode = "200", description = "다시 로그인할 주소")
  @ApiResponse(
      responseCode = "400",
      description = "WITHDRAWAL_PROVIDER_NOT_LINKED — provider가 이 계정에 연결된 소셜이 아니에요")
  WithdrawalResponse startWithdrawal(
      @Parameter(hidden = true) LoginUser user,
      @Parameter(
              description = "여러 소셜을 연결한 경우 고를 소셜 (kakao, naver, google, 대소문자 상관없어요). 비우면 처음 연결한 소셜",
              example = "kakao")
          String provider);

  @Operation(
      summary = "내 정보",
      description =
          "닉네임·권한·연결한 소셜·가입 시각·연락용 이메일(없으면 null)을 줘요. "
              + "로그인하지 않았거나 탈퇴한 회원의 남은 access token이면 401이에요(프론트는 이걸로 로그인 여부를 확인해요).")
  MeResponse me(@Parameter(hidden = true) LoginUser user);

  @Operation(
      summary = "내 제보",
      description = "공고·혜택·창업지원 사업·생활권·일반 제보를 합쳐 최근 것부터 100건까지 줘요. 처리 상태·결과·관리자 답이 같이 와요.")
  MyReportsResponse myReports(@Parameter(hidden = true) LoginUser user);

  @Operation(
      summary = "연락용 이메일 등록·변경",
      description =
          "선택 항목이에요(가입 마무리 화면·마이페이지). 약관·개인정보처리방침 변경, 이용 제한, 계정 안내처럼 꼭 알려야 할 때만 쓰고 알림 메일·광고는 보내지"
              + " 않아요. 인증 코드는 받지 않아요. 화면이 보여 준 동의 문구 버전(consentVersion, 예: email-v1)을 같이 보내요. 같은"
              + " 주소로 다시 보내도 동의 버전·시각을 새로 남겨요. 저장한 주소는 GET /api/users/me의 email로 확인해요.")
  @ApiResponse(responseCode = "204", description = "저장했어요")
  @ApiResponse(
      responseCode = "400",
      description =
          "VALIDATION_FAILED — email이 비었거나 이메일 형식이 아니거나 254자를 넘어요. "
              + "consentVersion이 비었거나 영문·숫자·점·하이픈 20자를 벗어나요")
  @ApiResponse(responseCode = "409", description = "EMAIL_ALREADY_USED — 다른 회원이 쓰는 주소예요 (대소문자 무시)")
  ResponseEntity<Void> changeEmail(
      @Parameter(hidden = true) LoginUser user, ContactEmailRequest request);

  @Operation(summary = "연락용 이메일 삭제", description = "동의 철회예요. 등록한 주소가 없어도 204예요.")
  @ApiResponse(responseCode = "204", description = "지웠어요")
  ResponseEntity<Void> removeEmail(@Parameter(hidden = true) LoginUser user);
}
