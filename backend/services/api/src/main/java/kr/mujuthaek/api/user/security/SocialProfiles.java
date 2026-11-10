package kr.mujuthaek.api.user.security;

import java.util.Map;
import kr.mujuthaek.api.common.exception.CustomException;
import kr.mujuthaek.api.common.exception.ErrorCode;
import kr.mujuthaek.api.user.domain.SocialProvider;
import kr.mujuthaek.api.user.service.SocialProfile;

/** 제공자마다 다른 회원 정보 응답 → {@link SocialProfile}. 회원번호와 닉네임만 꺼내요. */
final class SocialProfiles {

  private SocialProfiles() {}

  static SocialProfile from(String registrationId, Map<String, Object> attributes) {
    SocialProvider provider =
        SocialProvider.fromRegistrationId(registrationId)
            .orElseThrow(
                () -> new CustomException(ErrorCode.UNSUPPORTED_SOCIAL_PROVIDER, registrationId));
    return switch (provider) {
      case KAKAO -> kakao(attributes);
      case NAVER -> naver(attributes);
      case GOOGLE -> google(attributes);
    };
  }

  /**
   * 카카오 /v2/user/me: {"id": 1234567890, "properties": {"nickname": "…"}, "kakao_account":
   * {"profile": {"nickname": "…"}}}. 닉네임은 kakao_account.profile을 먼저 보고, 없으면 properties를 봐요.
   */
  private static SocialProfile kakao(Map<String, Object> attributes) {
    Object id = attributes.get("id");
    if (id == null) {
      throw new CustomException(ErrorCode.VALIDATION_FAILED, "카카오 회원번호가 없어요");
    }
    String nickname = text(child(child(attributes, "kakao_account"), "profile").get("nickname"));
    if (nickname == null) {
      nickname = text(child(attributes, "properties").get("nickname"));
    }
    return new SocialProfile(SocialProvider.KAKAO, String.valueOf(id), nickname);
  }

  /**
   * 네이버 /v1/nid/me: {"resultcode": "00", "message": "success", "response": {"id": "…", "nickname":
   * "…"}}.
   */
  private static SocialProfile naver(Map<String, Object> attributes) {
    Map<String, Object> response = child(attributes, "response");
    String id = text(response.get("id"));
    if (id == null) {
      throw new CustomException(ErrorCode.VALIDATION_FAILED, "네이버 회원번호가 없어요");
    }
    return new SocialProfile(SocialProvider.NAVER, id, text(response.get("nickname")));
  }

  /** 구글 /oauth2/v3/userinfo (scope profile): {"sub": "1078…", "name": "…", "given_name": "…"}. */
  private static SocialProfile google(Map<String, Object> attributes) {
    String id = text(attributes.get("sub"));
    if (id == null) {
      throw new CustomException(ErrorCode.VALIDATION_FAILED, "구글 회원번호가 없어요");
    }
    String nickname = text(attributes.get("name"));
    return new SocialProfile(
        SocialProvider.GOOGLE,
        id,
        nickname != null ? nickname : text(attributes.get("given_name")));
  }

  @SuppressWarnings("unchecked")
  private static Map<String, Object> child(Map<String, Object> parent, String key) {
    return parent.get(key) instanceof Map<?, ?> map ? (Map<String, Object>) map : Map.of();
  }

  private static String text(Object value) {
    return value instanceof String s && !s.isBlank() ? s : null;
  }
}
