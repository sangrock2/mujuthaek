package kr.mujuthaek.api.notice.dto.request;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

/**
 * 공고 제보. 맞는 값(reportedValue)이나 설명(note) 중 하나는 있어야 해요. 소득·자산 같은 개인 정보는 받지 않아요.
 *
 * @param field 화면의 칸 이름 (보증금, 신청 마감 …)
 * @param currentValue 화면에 보인 값
 * @param reportedValue 맞다고 생각하는 값
 * @param note 설명 (원문 몇 쪽에 있는지 등)
 * @param screen 제보한 화면 (공고 상세 · 내 집 …)
 */
public record NoticeReportRequest(
    @NotBlank @Size(max = 50) String field,
    @Size(max = 200) String currentValue,
    @Size(max = 200) String reportedValue,
    @Size(max = 1000) String note,
    @Size(max = 50) String screen) {}
