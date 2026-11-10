package kr.mujuthaek.api.notice.controller.spec;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.tags.Tag;
import kr.mujuthaek.api.notice.dto.response.AdminActivityResponse;

@Tag(
    name = "관리자 처리 기록",
    description = "관리자들이 처리한 검수와 제보를 최근 순으로 모아 봐요. 권한 ACTIVITY가 있는 관리자만 부를 수 있어요.")
public interface AdminActivityApiSpec {

  @Operation(
      summary = "처리 기록",
      description =
          "최근 days일 동안 처리한 검수(공고·혜택)와 제보(생활권 제보 포함)를 처리한 시각 최근 순으로 최대 300줄 줘요. "
              + "검수 기록은 추출 서비스에서 받아요. 받지 못하면 reviewsError에 이유를 넣고 제보 기록만 줘요. "
              + "기준값 변경·권한 변경 기록은 여기에 없고 각 모듈 API에 있어요.")
  AdminActivityResponse activity(
      @Parameter(
              description = "최근 며칠 (기본 30, 1~90 밖이면 가까운 끝값으로 맞춰요. 응답의 days가 실제로 쓴 값)",
              example = "30")
          int days);
}
