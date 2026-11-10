package kr.mujuthaek.api.notice.dto.request;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

/**
 * 일반 제보: 공고·혜택·사업에 묶이지 않은 제보. 소득·자산 같은 개인 정보는 받지 않아요.
 *
 * @param field 종류: MISSING_NOTICE(빠진 공고·정책) · WRONG_INFO(틀린 정보) · APP_ERROR(화면 오류) · ETC(기타)
 * @param note 내용 (빠진 공고 이름·주소, 어떤 화면에서 무엇이 안 됐는지 등)
 * @param screen 제보한 화면 (검색 · 오류 화면 · 내 정보 …)
 * @param currentValue 화면에 보인 값이나 오류 코드 (있으면)
 */
public record GeneralReportRequest(
    @Schema(allowableValues = {"MISSING_NOTICE", "WRONG_INFO", "APP_ERROR", "ETC"})
        @NotBlank
        @Size(max = 50)
        String field,
    @NotBlank @Size(max = 1000) String note,
    @Size(max = 50) String screen,
    @Size(max = 200) String currentValue) {}
