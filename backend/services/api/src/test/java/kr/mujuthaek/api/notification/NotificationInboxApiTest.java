package kr.mujuthaek.api.notification;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import kr.mujuthaek.api.TestcontainersConfiguration;
import kr.mujuthaek.api.common.id.UuidV7;
import kr.mujuthaek.api.notification.repository.InboxRepository;
import kr.mujuthaek.api.notification.service.internal.InboxService;
import kr.mujuthaek.api.user.domain.SocialProvider;
import kr.mujuthaek.api.user.service.AuthTokenService;
import kr.mujuthaek.api.user.service.LoginUser;
import kr.mujuthaek.api.user.service.SocialLoginService;
import kr.mujuthaek.api.user.service.SocialProfile;
import kr.mujuthaek.api.user.service.WithdrawalService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.test.web.servlet.MockMvc;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

/** 알림함 API: 최근 순·커서, 안 읽은 것만, 읽음 처리, 남의 알림, 탈퇴, 90일 정리. */
@SpringBootTest(properties = "notification.inbox-purge.enabled=false")
@AutoConfigureMockMvc
@Import(TestcontainersConfiguration.class)
class NotificationInboxApiTest {

  private static final String ME = "/api/users/me/notifications";

  @Autowired MockMvc mvc;
  @Autowired SocialLoginService logins;
  @Autowired AuthTokenService tokens;
  @Autowired WithdrawalService withdrawals;
  @Autowired InboxRepository repository;
  @Autowired InboxService service;
  @Autowired JdbcClient jdbc;
  @Autowired JsonMapper json;

  @Test
  void needsLogin() throws Exception {
    mvc.perform(get(ME)).andExpect(status().isUnauthorized());
    mvc.perform(post(ME + "/read-all")).andExpect(status().isUnauthorized());
  }

  @Test
  void listsNewestFirstPageByPage() throws Exception {
    LoginUser me = login();
    List<UUID> ids = add(me.userId(), 3, Instant.now()); // 만든 순서: ids[0] → ids[2]

    JsonNode first = page(me, "?size=2");
    assertThat(first.path("items")).hasSize(2);
    assertThat(first.path("items").get(0).path("id").asString()).isEqualTo(ids.get(2).toString());
    assertThat(first.path("items").get(0).path("title").asString()).isEqualTo("정정: 공고 2");
    assertThat(first.path("items").get(0).path("target").path("type").asString())
        .isEqualTo("NOTICE");
    assertThat(first.path("items").get(0).path("readAt").isNull()).isTrue();
    assertThat(first.path("hasNext").asBoolean()).isTrue();

    JsonNode second = page(me, "?size=2&cursor=" + first.path("nextCursor").asString());
    assertThat(second.path("items")).hasSize(1);
    assertThat(second.path("items").get(0).path("id").asString()).isEqualTo(ids.get(0).toString());
    assertThat(second.path("hasNext").asBoolean()).isFalse();

    mvc.perform(get(ME + "?cursor=broken").header("Authorization", bearer(me)))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("INVALID_CURSOR"));
  }

  @Test
  void readMarksOnlyMineAndUnreadFilterFollows() throws Exception {
    LoginUser me = login();
    LoginUser other = login();
    List<UUID> mine = add(me.userId(), 2, Instant.now());
    UUID theirs = add(other.userId(), 1, Instant.now()).getFirst();

    mvc.perform(post(ME + "/" + mine.getFirst() + "/read").header("Authorization", bearer(me)))
        .andExpect(status().isNoContent());
    mvc.perform(post(ME + "/" + mine.getFirst() + "/read").header("Authorization", bearer(me)))
        .andExpect(status().isNoContent()); // 두 번 읽어도 괜찮아요
    mvc.perform(post(ME + "/" + theirs + "/read").header("Authorization", bearer(me)))
        .andExpect(status().isNotFound())
        .andExpect(jsonPath("$.code").value("NOTIFICATION_NOT_FOUND"));

    mvc.perform(get(ME + "/unread-count").header("Authorization", bearer(me)))
        .andExpect(jsonPath("$.count").value(1));
    JsonNode unread = page(me, "?unread=true");
    assertThat(unread.path("items")).hasSize(1);
    assertThat(unread.path("items").get(0).path("id").asString()).isEqualTo(mine.get(1).toString());

    mvc.perform(post(ME + "/read-all").header("Authorization", bearer(me)))
        .andExpect(status().isNoContent());
    mvc.perform(get(ME + "/unread-count").header("Authorization", bearer(me)))
        .andExpect(jsonPath("$.count").value(0));
    mvc.perform(get(ME + "/unread-count").header("Authorization", bearer(other)))
        .andExpect(jsonPath("$.count").value(1)); // 다른 회원 것은 그대로
  }

  @Test
  void sameAlertIsStoredOnce() {
    UUID user = UUID.randomUUID();
    var entry = entry(user, "NOTICE:X:CORRECTED:2", Instant.now());

    assertThat(repository.addAll(List.of(entry))).isEqualTo(1);
    assertThat(repository.addAll(List.of(entry(user, "NOTICE:X:CORRECTED:2", Instant.now()))))
        .isZero();
  }

  @Test
  void withdrawalRemovesTheInbox() throws Exception {
    String socialId = "inbox-" + UUID.randomUUID();
    LoginUser me = logins.login(new SocialProfile(SocialProvider.KAKAO, socialId, "닉네임"));
    add(me.userId(), 2, Instant.now());

    withdrawals.withdraw(me.userId(), SocialProvider.KAKAO, socialId);

    assertThat(count(me.userId())).isZero();
  }

  @Test
  void purgeRemovesOnlyAlertsOlderThanNinetyDays() {
    UUID user = UUID.randomUUID();
    repository.addAll(
        List.of(
            entry(
                user,
                "old",
                Instant.now().minus(InboxService.RETENTION).minus(Duration.ofHours(1))),
            entry(user, "recent", Instant.now().minus(Duration.ofDays(89)))));

    service.purgeExpired();

    assertThat(
            jdbc.sql("select dedup_key from notification.notifications where user_id = :u")
                .param("u", user)
                .query(String.class)
                .list())
        .containsExactly("recent");
  }

  private JsonNode page(LoginUser user, String query) throws Exception {
    return json.readTree(
        mvc.perform(get(ME + query).header("Authorization", bearer(user)))
            .andExpect(status().isOk())
            .andReturn()
            .getResponse()
            .getContentAsString());
  }

  private List<UUID> add(UUID userId, int n, Instant at) {
    List<InboxRepository.NewEntry> entries = new ArrayList<>();
    for (int i = 0; i < n; i++) {
      entries.add(
          entry(userId, "NOTICE:" + UUID.randomUUID() + ":CORRECTED:" + i, at, "정정: 공고 " + i));
    }
    repository.addAll(entries);
    return entries.stream().map(InboxRepository.NewEntry::id).toList();
  }

  private static InboxRepository.NewEntry entry(UUID userId, String dedupKey, Instant at) {
    return entry(userId, dedupKey, at, "정정: 공고");
  }

  private static InboxRepository.NewEntry entry(
      UUID userId, String dedupKey, Instant at, String title) {
    UUID target = UUID.randomUUID();
    return new InboxRepository.NewEntry(
        UuidV7.next(),
        userId,
        "CORRECTED",
        "NOTICE",
        target,
        title,
        "관심 공고의 일정 내용이 바뀌었어요.",
        "/notices/" + target,
        dedupKey,
        at);
  }

  private long count(UUID userId) {
    return jdbc.sql("select count(*) from notification.notifications where user_id = :u")
        .param("u", userId)
        .query(Long.class)
        .single();
  }

  private LoginUser login() {
    return logins.login(
        new SocialProfile(SocialProvider.KAKAO, "inbox-" + UUID.randomUUID(), "닉네임"));
  }

  private String bearer(LoginUser user) {
    return "Bearer " + tokens.issue(user).accessToken();
  }
}
