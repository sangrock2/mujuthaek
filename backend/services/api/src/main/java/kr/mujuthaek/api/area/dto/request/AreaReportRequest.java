package kr.mujuthaek.api.area.dto.request;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

/**
 * 생활권 제보. 맞는 값(reportedValue)이나 설명(note) 중 하나는 있어야 해요.
 *
 * @param noticeLocationId 단지가 여럿인 공고면 공고 상세 locations[].id
 * @param field 화면의 항목 이름 (역까지 거리 …)
 */
public record AreaReportRequest(
    @Size(max = 100) String noticeLocationId,
    @NotBlank @Size(max = 50) String field,
    @Size(max = 200) String currentValue,
    @Size(max = 200) String reportedValue,
    @Size(max = 1000) String note,
    @Size(max = 50) String screen) {}
