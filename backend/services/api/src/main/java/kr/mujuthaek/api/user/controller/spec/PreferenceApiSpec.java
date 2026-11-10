package kr.mujuthaek.api.user.controller.spec;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.util.UUID;
import kr.mujuthaek.api.common.dto.response.CursorPageResponse;
import kr.mujuthaek.api.user.dto.request.InterestRequests;
import kr.mujuthaek.api.user.dto.request.NotificationSettingsRequest;
import kr.mujuthaek.api.user.dto.response.FavoriteResponse;
import kr.mujuthaek.api.user.dto.response.InterestResponses;
import kr.mujuthaek.api.user.dto.response.NotificationSettingsResponse;
import kr.mujuthaek.api.user.service.LoginUser;
import org.springframework.http.ResponseEntity;

@Tag(
    name = "관심·알림 설정",
    description = "관심 공고·정책, 관심 조건, 알림 설정이에요. 로그인한 회원만 부를 수 있고, 알림을 받을 회원을 고르는 데 써요.")
public interface PreferenceApiSpec {

  @Operation(
      summary = "관심 공고·정책 저장",
      description =
          "이미 저장했으면 그대로 204예요(처음 저장한 시각 유지). 다른 공고에 합쳐진 공고는 남은 공고로 저장해요. "
              + "저장한 공고는 정정·후속 안내·마감 D-3·D-1 알림을 받아요.")
  @ApiResponse(responseCode = "204", description = "저장했어요")
  @ApiResponse(
      responseCode = "400",
      description =
          "VALIDATION_FAILED — targetType이 NOTICE·BENEFIT·STARTUP_SUPPORT·SPACE_RECRUITMENT 중 하나가"
              + " 아니에요")
  @ApiResponse(
      responseCode = "404",
      description = "FAVORITE_TARGET_NOT_FOUND — 그 종류의 공고·정책이 없거나 숨긴 혜택이에요")
  @ApiResponse(responseCode = "409", description = "FAVORITE_LIMIT_EXCEEDED — 이미 200개를 저장했어요")
  ResponseEntity<Void> addFavorite(
      @Parameter(hidden = true) LoginUser user,
      @Parameter(
              description = "NOTICE · BENEFIT · STARTUP_SUPPORT · SPACE_RECRUITMENT (대소문자 상관없어요)",
              example = "NOTICE")
          String targetType,
      @Parameter(description = "공고·혜택·정책 ID") UUID targetId);

  @Operation(summary = "관심 공고·정책 지우기", description = "저장하지 않았어도 204예요.")
  @ApiResponse(responseCode = "204", description = "지웠어요")
  @ApiResponse(
      responseCode = "400",
      description =
          "VALIDATION_FAILED — targetType이 NOTICE·BENEFIT·STARTUP_SUPPORT·SPACE_RECRUITMENT 중 하나가"
              + " 아니에요")
  ResponseEntity<Void> removeFavorite(
      @Parameter(hidden = true) LoginUser user,
      @Parameter(
              description = "NOTICE · BENEFIT · STARTUP_SUPPORT · SPACE_RECRUITMENT (대소문자 상관없어요)",
              example = "NOTICE")
          String targetType,
      @Parameter(description = "공고·혜택·정책 ID") UUID targetId);

  @Operation(
      summary = "내 관심 공고·정책 목록",
      description =
          "최근 저장한 것부터 줘요. 제목·기관·상태·신청 기간·화면 주소를 같이 주고, 대상이 사라졌으면 제목이 null이에요. "
              + "응답의 nextCursor를 다음 요청의 cursor로 넘기면 이어서 받아요(hasNext가 false면 끝). "
              + "targetType을 바꾸면 이전 cursor는 쓸 수 없어요.")
  @ApiResponse(responseCode = "200", description = "관심 공고·정책 목록")
  @ApiResponse(
      responseCode = "400",
      description =
          "VALIDATION_FAILED — targetType이 NOTICE·BENEFIT·STARTUP_SUPPORT·SPACE_RECRUITMENT가 아니거나"
              + " size가 1~100 밖이에요. INVALID_CURSOR — cursor가 올바르지 않거나 다른 targetType으로 받은 거예요")
  CursorPageResponse<FavoriteResponse> favorites(
      @Parameter(hidden = true) LoginUser user,
      @Parameter(
              description =
                  "거를 종류: NOTICE · BENEFIT · STARTUP_SUPPORT · SPACE_RECRUITMENT (대소문자 상관없어요). 비우면"
                      + " 모두")
          String targetType,
      @Parameter(description = "이전 응답의 nextCursor. 첫 요청이면 비워요") String cursor,
      @Parameter(description = "한 번에 받을 개수 (기본 20, 1~100)", example = "20") Integer size);

  @Operation(
      summary = "주거 관심 조건",
      description =
          "저장한 적 없으면 saved가 false이고 빈 목록과 includeNationwide true를 줘요(이때는 새 소식 알림을 받지 않아요).")
  InterestResponses.Housing housing(@Parameter(hidden = true) LoginUser user);

  @Operation(
      summary = "주거 관심 조건 저장",
      description =
          "저장하면 새 주거 공고 알림 대상이 돼요(지역·전국 여부·공고 유형으로 골라요). 보낸 값으로 통째로 바꾸고 저장한 값을 돌려줘요. regionCodes는"
              + " 시군구 5자리 또는 시도 전체 xx000이고 지금 유효한 코드만 받아요. 목록마다 30개까지이고 중복은 한 번만 저장해요."
              + " includeNationwide를 비우면 true예요. noticeTypes는 공고 유형 코드(예: HAPPY_HOUSING)이고 비우면 모든"
              + " 유형이에요.")
  @ApiResponse(responseCode = "200", description = "저장한 관심 조건")
  @ApiResponse(
      responseCode = "400",
      description =
          "VALIDATION_FAILED — regionCodes가 5자리가 아니거나 없거나 폐지된 코드예요. 목록이 30개를 넘거나 "
              + "noticeTypes가 영문 대문자·숫자·_ 형식이 아니에요")
  InterestResponses.Housing saveHousing(
      @Parameter(hidden = true) LoginUser user, InterestRequests.Housing body);

  @Operation(
      summary = "사업공간·창업지원 관심 조건",
      description =
          "저장한 적 없으면 saved가 false이고 빈 목록과 includeNationwide true를 줘요(이때는 새 소식 알림을 받지 않아요).")
  InterestResponses.Business business(@Parameter(hidden = true) LoginUser user);

  @Operation(
      summary = "사업공간·창업지원 관심 조건 저장",
      description =
          "저장하면 새 사업공간 공고·창업지원 사업·사업공간 모집 알림 대상이 돼요(지역·전국 여부로 골라요). 보낸 값으로 통째로 바꾸고 저장한 값을 돌려줘요. "
              + "regionCodes는 시군구 5자리 또는 시도 전체 xx000이고 지금 유효한 코드만 받아요. 목록마다 30개까지이고 중복은 한 번만 저장해요. "
              + "includeNationwide를 비우면 true예요. industryCodes는 표준산업분류 대분류 A~U, "
              + "startupStages는 PRE_STARTUP · OPERATING이고 비우면 전부예요. "
              + "업종·창업 단계는 지금은 저장만 하고 알림 대상을 고를 때는 쓰지 않아요.")
  @ApiResponse(responseCode = "200", description = "저장한 관심 조건")
  @ApiResponse(
      responseCode = "400",
      description =
          "VALIDATION_FAILED — regionCodes가 5자리가 아니거나 없거나 폐지된 코드예요. 목록이 30개를 넘거나 "
              + "industryCodes·startupStages에 모르는 값이 있어요")
  InterestResponses.Business saveBusiness(
      @Parameter(hidden = true) LoginUser user, InterestRequests.Business body);

  @Operation(
      summary = "지원 정책 관심 조건",
      description =
          "저장한 적 없으면 saved가 false이고 빈 목록과 includeNationwide true를 줘요(이때는 새 소식 알림을 받지 않아요).")
  InterestResponses.Support support(@Parameter(hidden = true) LoginUser user);

  @Operation(
      summary = "지원 정책 관심 조건 저장",
      description =
          "저장하면 새 지원 정책(혜택) 알림 대상이 돼요(지역·전국 여부로 골라요). 보낸 값으로 통째로 바꾸고 저장한 값을 돌려줘요. regionCodes는 혜택"
              + " 관심 지역(보통 사는 곳)으로, 시군구 5자리 또는 시도 전체 xx000이고 지금 유효한 코드만 받아요. 목록마다 30개까지이고 중복은 한 번만"
              + " 저장해요. includeNationwide를 비우면 true예요. supportKinds는 RENT · DEPOSIT_LOAN ·"
              + " PURCHASE_LOAN · HOUSING_SUPPLY · MOVE_IN_GRANT · CASH이고 비우면 전부예요. 지원 종류는 지금은 저장만"
              + " 하고 알림 대상을 고를 때는 쓰지 않아요.")
  @ApiResponse(responseCode = "200", description = "저장한 관심 조건")
  @ApiResponse(
      responseCode = "400",
      description =
          "VALIDATION_FAILED — regionCodes가 5자리가 아니거나 없거나 폐지된 코드예요. 목록이 30개를 넘거나 "
              + "supportKinds에 모르는 값이 있어요")
  InterestResponses.Support saveSupport(
      @Parameter(hidden = true) LoginUser user, InterestRequests.Support body);

  @Operation(
      summary = "관심 조건 지우기",
      description = "그 종류의 새 소식 알림을 그만 받아요. 관심 공고·정책 알림은 그대로예요. 저장한 적 없어도 204예요.")
  @ApiResponse(responseCode = "204", description = "지웠어요")
  @ApiResponse(
      responseCode = "404",
      description = "NOT_FOUND — kind가 housing·business·support가 아니에요")
  ResponseEntity<Void> deleteInterest(
      @Parameter(hidden = true) LoginUser user,
      @Parameter(description = "housing · business · support (소문자)", example = "housing")
          String kind);

  @Operation(
      summary = "알림 설정",
      description =
          "알림 종류별 켬·끔과 조용한 시간이에요. 저장한 적 없으면 기본값(모두 켬, 조용한 시간 끔)을 줘요. "
              + "끈 종류도 알림함에는 남아요(웹 푸시·이메일로 보내지 않을 뿐).")
  NotificationSettingsResponse notificationSettings(@Parameter(hidden = true) LoginUser user);

  @Operation(
      summary = "알림 설정 저장",
      description =
          "모든 칸(newNotice·newSupport·deadline·correction·followUp·quietEnabled)을 보내요. "
              + "quietEnabled를 켜면 22:00~08:00 알림을 08:00에 보내요. 웹 푸시 자체의 켬·끔은 기기 구독이라 여기 없어요. "
              + "저장한 값을 돌려줘요.")
  @ApiResponse(responseCode = "200", description = "저장한 알림 설정")
  @ApiResponse(responseCode = "400", description = "VALIDATION_FAILED — 빠진 칸이 있어요")
  NotificationSettingsResponse saveNotificationSettings(
      @Parameter(hidden = true) LoginUser user, NotificationSettingsRequest b);
}
