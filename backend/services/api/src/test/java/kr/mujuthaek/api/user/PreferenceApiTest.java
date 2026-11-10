package kr.mujuthaek.api.user;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.time.Instant;
import java.util.UUID;
import kr.mujuthaek.api.TestcontainersConfiguration;
import kr.mujuthaek.api.user.domain.SocialProvider;
import kr.mujuthaek.api.user.repository.FavoriteRepository;
import kr.mujuthaek.api.user.service.AuthTokenService;
import kr.mujuthaek.api.user.service.LoginUser;
import kr.mujuthaek.api.user.service.SocialLoginService;
import kr.mujuthaek.api.user.service.SocialProfile;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;
import tools.jackson.databind.json.JsonMapper;

/** 관심 조건·알림 설정·관심 공고 API: 기본값, 저장, 검사, 로그인. */
@SpringBootTest
@AutoConfigureMockMvc
@Import(TestcontainersConfiguration.class)
class PreferenceApiTest {

  @Autowired MockMvc mvc;
  @Autowired SocialLoginService logins;
  @Autowired AuthTokenService tokens;
  @Autowired FavoriteRepository favorites;
  @Autowired JsonMapper json;

  @Test
  void needsLogin() throws Exception {
    mvc.perform(get("/api/users/me/interests/housing")).andExpect(status().isUnauthorized());
    mvc.perform(get("/api/users/me/notification-settings")).andExpect(status().isUnauthorized());
  }

  @Test
  void housingInterestIsSavedCheckedAndDeleted() throws Exception {
    LoginUser me = login();
    mvc.perform(as(me, get("/api/users/me/interests/housing")))
        .andExpect(jsonPath("$.saved").value(false))
        .andExpect(jsonPath("$.includeNationwide").value(true));

    mvc.perform(
            as(me, put("/api/users/me/interests/housing"))
                .content(
                    "{\"regionCodes\":[\"11440\",\"11000\",\"11440\"],\"includeNationwide\":false,\"noticeTypes\":[\"HAPPY_HOUSING\"]}"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.regionCodes.length()").value(2)) // 같은 코드는 한 번
        .andExpect(jsonPath("$.includeNationwide").value(false));
    mvc.perform(as(me, get("/api/users/me/interests/housing")))
        .andExpect(jsonPath("$.saved").value(true))
        .andExpect(jsonPath("$.regionCodes[0]").value("11440"))
        .andExpect(jsonPath("$.noticeTypes[0]").value("HAPPY_HOUSING"));

    mvc.perform(
            as(me, put("/api/users/me/interests/housing")).content("{\"regionCodes\":[\"99999\"]}"))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.detail").value("regionCodes: 없거나 폐지된 지역 코드예요: 99999"));
    mvc.perform(
            as(me, put("/api/users/me/interests/housing")).content("{\"regionCodes\":[\"서울\"]}"))
        .andExpect(status().isBadRequest());

    mvc.perform(as(me, delete("/api/users/me/interests/housing")))
        .andExpect(status().isNoContent());
    mvc.perform(as(me, get("/api/users/me/interests/housing")))
        .andExpect(jsonPath("$.saved").value(false));
    mvc.perform(as(me, delete("/api/users/me/interests/pets"))).andExpect(status().isNotFound());
  }

  @Test
  void businessAndSupportInterestsCheckTheirCodes() throws Exception {
    LoginUser me = login();
    mvc.perform(
            as(me, put("/api/users/me/interests/business"))
                .content(
                    "{\"regionCodes\":[\"11440\"],\"industryCodes\":[\"C\",\"J\"],\"startupStages\":[\"PRE_STARTUP\"]}"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.industryCodes.length()").value(2));
    mvc.perform(
            as(me, put("/api/users/me/interests/business")).content("{\"industryCodes\":[\"Z\"]}"))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.detail").value("industryCodes: 모르는 값이에요: Z"));
    mvc.perform(
            as(me, put("/api/users/me/interests/support"))
                .content("{\"regionCodes\":[\"11000\"],\"supportKinds\":[\"RENT\"]}"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.supportKinds[0]").value("RENT"));
    mvc.perform(
            as(me, put("/api/users/me/interests/support"))
                .content("{\"supportKinds\":[\"LOTTO\"]}"))
        .andExpect(status().isBadRequest());
  }

  @Test
  void notificationSettingsDefaultToAllOnAndNeedEveryField() throws Exception {
    LoginUser me = login();
    mvc.perform(as(me, get("/api/users/me/notification-settings")))
        .andExpect(jsonPath("$.newNotice").value(true))
        .andExpect(jsonPath("$.deadline").value(true))
        .andExpect(jsonPath("$.quietEnabled").value(false));

    mvc.perform(
            as(me, put("/api/users/me/notification-settings"))
                .content(
                    "{\"newNotice\":false,\"newSupport\":true,\"deadline\":true,\"correction\":true,\"followUp\":false,\"quietEnabled\":true}"))
        .andExpect(status().isOk());
    mvc.perform(as(me, get("/api/users/me/notification-settings")))
        .andExpect(jsonPath("$.newNotice").value(false))
        .andExpect(jsonPath("$.followUp").value(false))
        .andExpect(jsonPath("$.quietEnabled").value(true));

    mvc.perform(as(me, put("/api/users/me/notification-settings")).content("{\"newNotice\":true}"))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"));
  }

  @Test
  void favoriteOfSomethingThatDoesNotExistIs404() throws Exception {
    LoginUser me = login();
    mvc.perform(as(me, put("/api/users/me/favorites/notice/" + UUID.randomUUID())))
        .andExpect(status().isNotFound())
        .andExpect(jsonPath("$.code").value("FAVORITE_TARGET_NOT_FOUND"));
    mvc.perform(as(me, put("/api/users/me/favorites/house/" + UUID.randomUUID())))
        .andExpect(status().isBadRequest());
    mvc.perform(as(me, get("/api/users/me/favorites")))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.items.length()").value(0));
  }

  @Test
  void favoritesListNewestFirstWithCursorAndFilter() throws Exception {
    LoginUser me = login();
    UUID first = UUID.randomUUID();
    UUID second = UUID.randomUUID();
    UUID space = UUID.randomUUID();
    favorites.add(me.userId(), "NOTICE", first, Instant.parse("2026-10-20T00:00:00Z"));
    favorites.add(me.userId(), "NOTICE", second, Instant.parse("2026-10-21T00:00:00Z"));
    favorites.add(me.userId(), "SPACE_RECRUITMENT", space, Instant.parse("2026-10-22T00:00:00Z"));

    String cursor =
        json.readTree(
                mvc.perform(as(me, get("/api/users/me/favorites?targetType=notice&size=1")))
                    .andExpect(jsonPath("$.items[0].targetId").value(second.toString()))
                    .andExpect(jsonPath("$.hasNext").value(true))
                    .andReturn()
                    .getResponse()
                    .getContentAsString())
            .path("nextCursor")
            .asString();
    mvc.perform(as(me, get("/api/users/me/favorites?targetType=NOTICE&size=1&cursor=" + cursor)))
        .andExpect(jsonPath("$.items[0].targetId").value(first.toString()))
        .andExpect(jsonPath("$.hasNext").value(false));
    // 거르는 종류가 다르면 처음부터
    mvc.perform(as(me, get("/api/users/me/favorites?cursor=" + cursor)))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("INVALID_CURSOR"));
    mvc.perform(as(me, get("/api/users/me/favorites")))
        .andExpect(jsonPath("$.items[0].targetType").value("SPACE_RECRUITMENT"))
        .andExpect(jsonPath("$.items.length()").value(3));

    mvc.perform(as(me, delete("/api/users/me/favorites/notice/" + second)))
        .andExpect(status().isNoContent());
    mvc.perform(as(me, delete("/api/users/me/favorites/notice/" + second)))
        .andExpect(status().isNoContent());
    mvc.perform(as(me, get("/api/users/me/favorites?targetType=NOTICE")))
        .andExpect(jsonPath("$.items.length()").value(1));
  }

  @Test
  void interestLimitsAndWholeCityCodes() throws Exception {
    LoginUser me = login();
    String many =
        java.util.stream.IntStream.range(0, 31)
            .mapToObj(i -> "\"11440\"".replace("11440", String.valueOf(11000 + i)))
            .collect(java.util.stream.Collectors.joining(","));
    mvc.perform(
            as(me, put("/api/users/me/interests/support"))
                .content("{\"regionCodes\":[" + many + "]}"))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.detail").value("regionCodes: 30개까지예요"));
    mvc.perform(
            as(me, put("/api/users/me/interests/support")).content("{\"regionCodes\":[\"99000\"]}"))
        .andExpect(status().isBadRequest());
    mvc.perform(as(me, get("/api/users/me/interests/business")))
        .andExpect(jsonPath("$.saved").value(false));
    mvc.perform(as(me, get("/api/users/me/interests/support")))
        .andExpect(jsonPath("$.saved").value(false));
    mvc.perform(
            as(me, put("/api/users/me/interests/support")).content("{\"regionCodes\":[\"26000\"]}"))
        .andExpect(status().isOk());
    mvc.perform(as(me, get("/api/users/me/interests/support")))
        .andExpect(jsonPath("$.saved").value(true))
        .andExpect(jsonPath("$.regionCodes[0]").value("26000"));
    mvc.perform(as(me, put("/api/users/me/interests/business")).content("{}"))
        .andExpect(status().isOk());
    mvc.perform(as(me, get("/api/users/me/interests/business")))
        .andExpect(jsonPath("$.saved").value(true))
        .andExpect(jsonPath("$.includeNationwide").value(true));
  }

  private MockHttpServletRequestBuilder as(LoginUser user, MockHttpServletRequestBuilder request) {
    return request
        .header("Authorization", "Bearer " + tokens.issue(user).accessToken())
        .contentType(MediaType.APPLICATION_JSON);
  }

  private LoginUser login() {
    return logins.login(
        new SocialProfile(SocialProvider.KAKAO, "pref-" + UUID.randomUUID(), "닉네임"));
  }
}
