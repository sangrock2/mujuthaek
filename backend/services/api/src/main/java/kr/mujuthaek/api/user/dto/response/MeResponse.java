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
 * @param termsAgreed 가입 필수 동의(만 14세 이상·이용약관·개인정보 수집·이용)를 했는지. false면 프론트가 동의 화면으로 보내요 (동의 전에는 회원
 *     기능이 403 TERMS_NOT_AGREED)
 */
public record MeResponse(
    UUID id,
    String nickname,
    String role,
    List<String> providers,
    Instant joinedAt,
    String email,
    boolean termsAgreed) {}
