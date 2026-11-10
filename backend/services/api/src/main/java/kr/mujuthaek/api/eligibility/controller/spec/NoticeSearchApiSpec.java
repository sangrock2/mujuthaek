package kr.mujuthaek.api.eligibility.controller.spec;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.tags.Tag;
import kr.mujuthaek.api.eligibility.dto.request.NoticeSearchRequest;
import kr.mujuthaek.api.eligibility.dto.response.NoticeSearchResponse;
import org.springframework.http.ResponseEntity;

@Tag(
    name = "공고 맞춤 목록",
    description =
        "판정 입력으로 판정한 공고 목록이에요. 판정 입력이 섞여서 GET이 아니라 POST예요. 로그인 없이 부를 수 있어요. "
            + "판정 입력은 저장하지 않고 응답은 캐시하지 않아요(no-store).")
public interface NoticeSearchApiSpec {

  @Operation(
      summary = "공고 맞춤 목록",
      description =
          "공개 목록(GET /api/v1/notices)과 같은 필터로 후보를 마감 임박순 최대 300개까지 고르고, 공고마다 판정과 준비할 돈을 계산해 정렬해요. "
              + "지원 불가 공고는 includeIneligible이 true일 때만 넣고, counts는 지원 불가를 빼기 전 개수예요. "
              + "sort는 RECOMMENDED(기본: 지원 가능 → 확인 필요 → 지원 불가, 같으면 마감 임박 → 생활권 총점) · DEADLINE · "
              + "PREPARE_COST(준비할 돈 적은 순) · AREA_SCORE(생활권 총점 높은 순)예요. "
              + "prepareCostWon은 주택형 중 가장 적은 준비할 돈이고, 모르면 null이며 이유는 prepareCostNote예요. "
              + "응답의 nextCursor를 다음 요청의 cursor로 넘기면 이어서 받아요(hasNext가 false면 끝).")
  @ApiResponse(responseCode = "200", description = "공고 목록")
  @ApiResponse(
      responseCode = "400",
      description =
          "VALIDATION_FAILED — 본문 형식이 맞지 않거나(size 1~100, sort 허용 값, applicant 값) 필터 값(field · tenure · "
              + "noticeTypes · statuses · regionCodes)이 허용 값이 아니에요. "
              + "INVALID_CURSOR — cursor가 올바르지 않거나 다른 정렬로 만든 거예요")
  ResponseEntity<NoticeSearchResponse> search(NoticeSearchRequest request);
}
