package kr.mujuthaek.api.user.domain;

import java.util.Arrays;
import java.util.Optional;

/** 소셜 로그인 제공자. 이름 소문자가 application.yml의 registration id예요 (kakao, naver, google). */
public enum SocialProvider {
  KAKAO,
  NAVER,
  GOOGLE;

  public static Optional<SocialProvider> fromRegistrationId(String registrationId) {
    return Arrays.stream(values())
        .filter(p -> p.name().equalsIgnoreCase(registrationId))
        .findFirst();
  }
}
