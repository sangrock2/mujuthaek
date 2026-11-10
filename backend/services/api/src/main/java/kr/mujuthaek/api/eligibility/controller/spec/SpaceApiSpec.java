package kr.mujuthaek.api.eligibility.controller.spec;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.util.UUID;
import kr.mujuthaek.api.eligibility.dto.request.SpaceEvaluateRequest;
import kr.mujuthaek.api.eligibility.dto.request.SpaceSearchRequest;
import kr.mujuthaek.api.eligibility.dto.response.SpaceEvaluationResponse;
import kr.mujuthaek.api.eligibility.dto.response.SpaceSearchResponse;
import org.springframework.http.ResponseEntity;

@Tag(
    name = "사업공간 맞춤 목록·판정",
    description =
        "열린 사업공간 공고와 사업공간 모집 정책(K-Startup·기업마당 입주기업 모집)의 맞춤 목록과 하나의 판정이에요. "
            + "로그인 없이 부를 수 있어요. 판정 입력은 저장하지 않고 응답은 캐시하지 않아요(no-store).")
public interface SpaceApiSpec {

  @Operation(
      summary = "사업공간 맞춤 목록",
      description =
          "열린 사업공간을 모두 판정하고 지역 · 종류(spaceTypes) · 검색어로 걸러요. 여러 출처에 올라온 같은 모집은 하나만 남겨요. "
              + "지원 불가는 includeIneligible이 true일 때만 넣고, counts는 지원 불가를 빼기 전 개수, "
              + "typeCounts는 종류 필터를 걸기 전 종류별 개수예요(종류 칩에 써요). includeIneligible과 상관없이 지원 불가도 들어 있어요. "
              + "sort는 RECOMMENDED(기본: 지원 가능 → 확인 필요 → 지원 불가, 같으면 마감 임박) · DEADLINE(마감 임박)이에요. "
              + "응답의 nextCursor를 다음 요청의 cursor로 넘기면 이어서 받아요(hasNext가 false면 끝).")
  @ApiResponse(responseCode = "200", description = "사업공간 목록")
  @ApiResponse(
      responseCode = "400",
      description =
          "VALIDATION_FAILED — 본문 형식이 맞지 않아요 (size 1~100, sort · spaceTypes · regionCodes 허용 값, applicant 값). "
              + "INVALID_CURSOR — cursor가 올바르지 않거나 다른 정렬로 만든 거예요")
  ResponseEntity<SpaceSearchResponse> search(SpaceSearchRequest request);

  @Operation(
      summary = "사업공간 하나 판정",
      description =
          "열린 사업공간 공고나 모집 정책 하나의 자격 판정과 기간 · 지역 · 출처 안내를 줘요. "
              + "공고면 상세 내용은 공고 상세(GET /api/v1/notices/{id})를 쓰고, 모집 정책(policy가 true)은 이 응답과 원문(detailUrl)으로 보여 줘요. "
              + "본문은 비워도 돼요. 판정 틀이 아직 없으면 judgment가 null이에요(화면은 \"자격 조건 정리 중\").")
  @ApiResponse(responseCode = "200", description = "판정 결과")
  @ApiResponse(responseCode = "400", description = "VALIDATION_FAILED — applicant 형식이 맞지 않아요")
  @ApiResponse(responseCode = "404", description = "NOTICE_NOT_FOUND — 열린 사업공간 공고나 모집 정책이 아니에요")
  ResponseEntity<SpaceEvaluationResponse> evaluate(
      @Parameter(description = "사업공간 공고 ID 또는 모집 정책 ID") UUID id, SpaceEvaluateRequest request);
}
