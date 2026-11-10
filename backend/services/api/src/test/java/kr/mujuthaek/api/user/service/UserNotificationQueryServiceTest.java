package kr.mujuthaek.api.user.service;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import kr.mujuthaek.api.TestcontainersConfiguration;
import kr.mujuthaek.api.user.domain.SocialProvider;
import kr.mujuthaek.api.user.repository.FavoriteRepository;
import kr.mujuthaek.api.user.repository.InterestRepository;
import kr.mujuthaek.api.user.repository.InterestRepository.Business;
import kr.mujuthaek.api.user.repository.InterestRepository.Housing;
import kr.mujuthaek.api.user.repository.InterestRepository.Support;
import kr.mujuthaek.api.user.repository.NotificationSettingRepository;
import kr.mujuthaek.api.user.repository.NotificationSettingRepository.Settings;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.simple.JdbcClient;

/**
 * 알림 대상자 고르기: 지역 맞추기(시군구·시도 전체), 전국, 공고 유형, 관심 공고, 설정 기본값. 서울(11)·마포구(11440)·강동구(11740)·부산
 * 해운대구(26350).
 */
@SpringBootTest
@Import(TestcontainersConfiguration.class)
class UserNotificationQueryServiceTest {

  @Autowired UserNotificationQueryService query;
  @Autowired InterestRepository interests;
  @Autowired FavoriteRepository favorites;
  @Autowired NotificationSettingRepository settings;
  @Autowired SocialLoginService logins;
  @Autowired JdbcClient jdbc;

  UUID mapo;
  UUID seoul;
  UUID busan;
  UUID nationwideOnly;
  UUID happyOnly;

  @BeforeEach
  void users() {
    jdbc.sql("delete from account.housing_interests").update();
    jdbc.sql("delete from account.business_interests").update();
    jdbc.sql("delete from account.support_interests").update();
    Instant now = Instant.now();
    mapo = user();
    seoul = user();
    busan = user();
    nationwideOnly = user();
    happyOnly = user();
    interests.saveHousing(mapo, new Housing(List.of("11440"), false, List.of()), now);
    interests.saveHousing(seoul, new Housing(List.of("11000"), false, List.of()), now);
    interests.saveHousing(busan, new Housing(List.of("26350"), true, List.of()), now);
    interests.saveHousing(nationwideOnly, new Housing(List.of(), true, List.of()), now);
    interests.saveHousing(
        happyOnly, new Housing(List.of("11440"), false, List.of("HAPPY_HOUSING")), now);
  }

  @Test
  void districtNoticeReachesThatDistrictAndWholeCityButNotOthers() {
    assertThat(query.newNoticeAudience("HOUSING", List.of("11440"), false, "NATIONAL_RENTAL"))
        .containsExactlyInAnyOrder(mapo, seoul); // happyOnly는 유형이 달라서 빠짐
    assertThat(query.newNoticeAudience("HOUSING", List.of("11440"), false, "HAPPY_HOUSING"))
        .containsExactlyInAnyOrder(mapo, seoul, happyOnly);
    assertThat(query.newNoticeAudience("HOUSING", List.of("11740"), false, null))
        .as("강동구 공고는 서울 전체만, 유형을 모르면 유형으로 거르지 않음")
        .containsExactlyInAnyOrder(seoul);
  }

  @Test
  void wholeCityNoticeReachesEveryDistrictOfThatCity() {
    assertThat(query.newNoticeAudience("HOUSING", List.of("11000"), false, null))
        .containsExactlyInAnyOrder(mapo, seoul, happyOnly);
  }

  @Test
  void nationwideNoticeReachesOnlyThoseWhoWantNationwide() {
    assertThat(query.newNoticeAudience("HOUSING", List.of(), true, null))
        .containsExactlyInAnyOrder(busan, nationwideOnly);
    assertThat(query.newNoticeAudience("BUSINESS_SPACE", List.of("11440"), false, null))
        .as("사업공간 공고는 business_interests")
        .isEmpty();
  }

  @Test
  void benefitsUseTheirOwnInterestsAndCityCodes() {
    Instant now = Instant.now();
    interests.saveSupport(mapo, new Support(List.of("11440"), false, List.of()), now);
    interests.saveSupport(busan, new Support(List.of("26350"), false, List.of()), now);
    interests.saveBusiness(seoul, new Business(List.of("11000"), true, List.of(), List.of()), now);

    assertThat(query.newBenefitAudience("BENEFIT", "SIDO", List.of("11")))
        .as("서울시 정책 → 마포구 회원")
        .containsExactly(mapo);
    assertThat(query.newBenefitAudience("BENEFIT", "SIGUNGU", List.of("26350")))
        .containsExactly(busan);
    assertThat(query.newBenefitAudience("STARTUP_SUPPORT", "NATIONWIDE", List.of()))
        .containsExactly(seoul);
    assertThat(query.newBenefitAudience("BENEFIT", "UNKNOWN", List.of("11"))).isEmpty();
  }

  @Test
  void favoritesAndSettings() {
    UUID notice = UUID.randomUUID();
    favorites.add(mapo, "NOTICE", notice, Instant.now());
    favorites.add(busan, "BENEFIT", notice, Instant.now()); // 같은 ID라도 종류가 다르면 다른 대상
    settings.save(mapo, new Settings(true, true, false, true, true, true), Instant.now());

    assertThat(query.favoriteAudience("NOTICE", notice)).containsExactly(mapo);

    Map<UUID, NotificationPreference> prefs = query.preferences(List.of(mapo, seoul));
    assertThat(prefs.get(mapo).enabled("DEADLINE_D1")).isFalse();
    assertThat(prefs.get(mapo).enabled("CORRECTED")).isTrue();
    assertThat(prefs.get(mapo).quietEnabled()).isTrue();
    assertThat(prefs.get(seoul)).isEqualTo(NotificationPreference.DEFAULT);
    assertThat(NotificationPreference.DEFAULT.enabled("SOMETHING_ELSE")).isFalse();
  }

  @Test
  void settingsOfAVeryLargeAudienceAreReadInChunks() {
    // 2026-11-10 코드 검토: 대상 전부를 IN 목록 하나에 넣어 6만 5천여 명부터 쿼리가 실패해 아무에게도 알림이 가지 않았음
    settings.save(mapo, new Settings(true, true, false, true, true, true), Instant.now());
    List<UUID> audience = new java.util.ArrayList<>();
    for (int i = 0; i < 70_000; i++) {
      audience.add(UUID.randomUUID());
    }
    audience.add(mapo);
    Map<UUID, NotificationPreference> prefs = query.preferences(audience);
    assertThat(prefs.get(mapo).enabled("DEADLINE_D1")).isFalse();
  }

  @Test
  void unknownFieldsHaveNoAudienceAndEachTypeMapsToItsSwitch() {
    assertThat(query.newNoticeAudience("ETC", List.of("11440"), true, null)).isEmpty();
    assertThat(query.newBenefitAudience("ETC", "NATIONWIDE", List.of())).isEmpty();
    assertThat(query.newBenefitAudience("BENEFIT", "SIGUNGU", null)).isEmpty();

    var p = new NotificationPreference(true, false, false, false, false, false);
    assertThat(p.enabled("NEW_NOTICE")).isTrue();
    assertThat(p.enabled("NEW_SUPPORT")).isFalse();
    assertThat(p.enabled("DEADLINE_D3")).isFalse();
    assertThat(p.enabled("FOLLOW_UP")).isFalse();
    assertThat(
            new NotificationPreference(false, true, false, false, true, false).enabled("FOLLOW_UP"))
        .isTrue();
  }

  private UUID user() {
    return logins
        .login(new SocialProfile(SocialProvider.KAKAO, "aud-" + UUID.randomUUID(), "닉네임"))
        .userId();
  }
}
