package kr.mujuthaek.api.common.dto.response;

import java.time.OffsetDateTime;
import java.util.UUID;

/**
 * 회원이 보낸 제보 하나 (내 정보의 「내 제보」). 공고·혜택·사업·일반 제보(notice)와 생활권 제보(area)가 같은 모양으로 와요.
 *
 * @param kind NOTICE · BENEFIT · PROGRAM · AREA · GENERAL
 * @param targetId 화면의 대상 ID (공고 ID, 혜택 ID, 창업지원 사업 ID). 일반 제보는 null
 * @param targetTitle 대상 제목. 모르면 null
 * @param field 제보한 칸 (일반 제보는 종류 MISSING_NOTICE · WRONG_INFO · APP_ERROR · ETC)
 * @param status NEW 받음 · DOING 확인 중 · DONE 처리 끝
 * @param result DONE일 때 FIXED 고침 · KEPT 그대로 둠
 * @param reply 관리자 답 (있으면)
 * @param linkPath 누르면 갈 화면 (일반 제보는 null)
 */
public record MyReportResponse(
    UUID id,
    String kind,
    UUID targetId,
    String targetTitle,
    String field,
    String reportedValue,
    String note,
    String status,
    String result,
    String reply,
    OffsetDateTime createdAt,
    OffsetDateTime handledAt,
    String linkPath) {}
