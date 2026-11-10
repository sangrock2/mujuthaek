package kr.mujuthaek.api.notice.dto.response;

import java.time.LocalDate;
import java.util.List;
import java.util.UUID;

/**
 * 공고 목록 한 줄. 값이 없으면 null로 내려가요.
 *
 * @param status 접수 상태. UNKNOWN은 일정이 없거나 확실하지 않아 단정할 수 없음(화면의 「확인 필요」)
 * @param needsCheck 원문 확인 전까지 보여 주지 않는 항목이 있음 (화면의 「확인 필요」 표시)
 * @param lat 대표 위치 좌표 (좌표가 있는 첫 위치, area가 못 찾았으면 null)
 * @param siteCount 위치 수 (단지·건물이 여럿이면 2 이상)
 * @param areaScore 위치 중 가장 높은 생활권 총점 0~100 (항목 같은 비중, 없으면 null)
 * @param tags 대표 위치의 세권 태그
 */
public record NoticeSummaryResponse(
    UUID id,
    String field,
    String title,
    String provider,
    String noticeType,
    String regionCode,
    String regionName,
    String status,
    LocalDate applyStart,
    LocalDate applyEnd,
    Integer dday,
    LocalDate postedOn,
    boolean needsCheck,
    Double lat,
    Double lng,
    int siteCount,
    Integer areaScore,
    List<String> tags) {}
