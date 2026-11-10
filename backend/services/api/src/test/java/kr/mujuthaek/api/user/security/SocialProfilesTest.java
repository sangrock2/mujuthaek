package kr.mujuthaek.api.user.security;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.Map;
import kr.mujuthaek.api.common.exception.CustomException;
import kr.mujuthaek.api.user.domain.SocialProvider;
import kr.mujuthaek.api.user.service.SocialProfile;
import org.junit.jupiter.api.Test;

class SocialProfilesTest {

  @Test
  void kakaoProfileNicknameFirst() {
    var attributes =
        Map.<String, Object>of(
            "id", 1234567890L,
            "properties", Map.of("nickname", "옛닉네임"),
            "kakao_account", Map.of("profile", Map.of("nickname", "무주택러")));
    assertThat(SocialProfiles.from("kakao", attributes))
        .isEqualTo(new SocialProfile(SocialProvider.KAKAO, "1234567890", "무주택러"));
  }

  @Test
  void kakaoWithoutAccountProfileUsesProperties() {
    var attributes = Map.<String, Object>of("id", 42L, "properties", Map.of("nickname", "닉"));
    assertThat(SocialProfiles.from("kakao", attributes).nickname()).isEqualTo("닉");
  }

  @Test
  void kakaoWithoutNicknameConsent() {
    assertThat(SocialProfiles.from("kakao", Map.of("id", 42L)).nickname()).isNull();
  }

  @Test
  void kakaoWithoutIdFails() {
    assertThatThrownBy(() -> SocialProfiles.from("kakao", Map.of("properties", Map.of())))
        .isInstanceOf(CustomException.class);
  }

  @Test
  void naverProfileIsInsideResponse() {
    var attributes =
        Map.<String, Object>of(
            "resultcode",
            "00",
            "message",
            "success",
            "response",
            Map.of("id", "abcDEF123", "nickname", "네이버닉"));
    assertThat(SocialProfiles.from("naver", attributes))
        .isEqualTo(new SocialProfile(SocialProvider.NAVER, "abcDEF123", "네이버닉"));
    assertThat(SocialProfiles.from("naver", Map.of("response", Map.of("id", "x"))).nickname())
        .isNull();
    assertThatThrownBy(() -> SocialProfiles.from("naver", Map.of("resultcode", "024")))
        .isInstanceOf(CustomException.class);
  }

  @Test
  void googleProfileUsesSubAndName() {
    assertThat(
            SocialProfiles.from(
                "google", Map.of("sub", "1078", "name", "구글이름", "given_name", "이름")))
        .isEqualTo(new SocialProfile(SocialProvider.GOOGLE, "1078", "구글이름"));
    assertThat(SocialProfiles.from("google", Map.of("sub", "1078", "given_name", "이름")).nickname())
        .isEqualTo("이름");
    assertThatThrownBy(() -> SocialProfiles.from("google", Map.of("name", "x")))
        .isInstanceOf(CustomException.class);
  }

  @Test
  void unknownProvider() {
    assertThatThrownBy(() -> SocialProfiles.from("facebook", Map.of("id", 1)))
        .isInstanceOf(CustomException.class);
  }
}
