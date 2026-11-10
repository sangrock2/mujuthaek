package kr.mujuthaek.api.user.dto.response;

import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

/**
 * 관심 공고·관심 정책 하나. 목록에 바로 그릴 수 있게 제목·기관·상태·신청 기간·화면 주소를 같이 줘요.
 *
 * @param targetType NOTICE · BENEFIT · STARTUP_SUPPORT · SPACE_RECRUITMENT
 * @param title 대상 제목. 대상이 내려갔거나 사라졌으면 null (목록에서 「사라진 공고」)
 * @param organization 공고는 공급 기관, 정책은 주관 기관
 * @param status 대상의 지금 상태 (공고 OPEN·CLOSED 등, 혜택 HIDDEN 포함). 사라졌으면 null
 * @param applyEnd 신청 마감일. 모르거나 상시면 null
 * @param linkPath 누르면 갈 화면 (알림과 같은 규칙, ScreenPaths)
 */
public record FavoriteResponse(
    String targetType,
    UUID targetId,
    Instant createdAt,
    String title,
    String organization,
    String status,
    LocalDate applyStart,
    LocalDate applyEnd,
    String linkPath) {}
