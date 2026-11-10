package kr.mujuthaek.api.area.domain;

import io.swagger.v3.oas.annotations.media.Schema;
import java.util.Map;
import java.util.UUID;

/**
 * 요청 때 계산한 위치 하나의 생활권 점수 (저장 안 함). API 문서 POST /areas/score의 한 줄이에요.
 *
 * @param siteId area 위치 ID
 * @param total 총점 0~100 (항목 점수가 하나도 없으면 null)
 * @param categoryScores 항목 점수 0~100. 직장(WORK)은 직장 위치를 받았을 때만
 * @param commuteMeters 직장까지 직선거리(m). 직장 위치가 없으면 null
 * @param commuteMinutes 통근 시간(분). 길찾기 API를 쓰지 않아 늘 null (화면은 직선거리를 보여요)
 */
public record SiteScore(
    UUID siteId,
    Integer total,
    @Schema(
            example =
                "{\"TRANSIT\": 85, \"SCHOOL\": 70, \"PARK\": 90, \"CONVENIENCE\": 60, \"HOSPITAL\": 55}")
        Map<LifeCategory, Integer> categoryScores,
    Long commuteMeters,
    Integer commuteMinutes) {}
