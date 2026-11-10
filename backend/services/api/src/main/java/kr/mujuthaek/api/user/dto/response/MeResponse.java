package kr.mujuthaek.api.user.dto.response;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

/**
 * 내 정보.
 *
 * @param role USER 또는 ADMIN
 * @param providers 이어진 소셜 로그인 (KAKAO, NAVER, GOOGLE)
 * @param email 계정 연락용 이메일. 등록하지 않았으면 null
 */
public record MeResponse(
    UUID id,
    String nickname,
    String role,
    List<String> providers,
    Instant joinedAt,
    String email) {}
