package kr.mujuthaek.api.eligibility.controller.spec;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.tags.Tag;
import kr.mujuthaek.api.eligibility.dto.request.HomeSummaryRequest;
import kr.mujuthaek.api.eligibility.dto.response.HomeSummaryResponse;
import org.springframework.http.ResponseEntity;

@Tag(
    name = "홈 요약",
    description =
        "내 조건으로 판정한 공고·혜택에서 홈 화면 카드에 쓰는 값만 골라 줘요. 로그인 없이 부를 수 있어요. "
            + "판정 입력은 저장하지 않고 응답은 캐시하지 않아요(no-store).")
public interface HomeSummaryApiSpec {

  @Operation(
      summary = "홈 요약",
      description =
          "공고 맞춤 목록(POST /api/v1/notices/search)과 같은 필터·판정 입력(구간 값)을 받아요. "
              + "homes는 상태별 공고 수와 최근 7일 안에 올라온 공고 수·7일 안에 마감하는 접수 중 공고 수, "
              + "news는 기간 제한 없이 공고일 최신순 공고(최대 4개, 7일보다 오래된 공고일 수 있어요), deadlines는 2주 안에 마감하는 접수 중 공고(마감 임박순, 최대 3개)예요. "
              + "지원 불가 공고는 새 공고·마감 수와 두 목록에 넣지 않아요. "
              + "혜택은 같은 찾아볼 지역으로 판정해 지원 가능·확인 필요 수와 1년에 받을 수 있는 돈(금액이 정해진 지원만, 대출 빼고), "
              + "그중 가장 많이 받는 지원 가능 혜택 하나(suggestedBenefit, 없으면 null)를 줘요.")
  @ApiResponse(responseCode = "200", description = "홈 요약")
  @ApiResponse(
      responseCode = "400",
      description =
          "VALIDATION_FAILED — 본문 형식이 맞지 않거나 필터 값(field · tenure · noticeTypes · statuses · regionCodes)이 "
              + "허용 값이 아니에요")
  ResponseEntity<HomeSummaryResponse> summary(HomeSummaryRequest request);
}
