package kr.mujuthaek.api.chat;

import static org.assertj.core.api.Assertions.assertThat;
import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.not;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.patch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.jayway.jsonpath.JsonPath;
import java.nio.charset.StandardCharsets;
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import kr.mujuthaek.api.TestcontainersConfiguration;
import kr.mujuthaek.api.chat.domain.ChatRoom;
import kr.mujuthaek.api.chat.service.ChatRooms;
import kr.mujuthaek.api.common.event.UserWithdrawn;
import kr.mujuthaek.api.user.domain.SocialProvider;
import kr.mujuthaek.api.user.service.AuthTokenService;
import kr.mujuthaek.api.user.service.LoginUser;
import kr.mujuthaek.api.user.service.SocialLoginService;
import kr.mujuthaek.api.user.service.SocialProfile;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.Primary;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

/**
 * 공고 채팅 API를 실제 스프링·DB·시큐리티로 불러요. 공고 모듈 대신 가짜 방({@link FakeRooms})을 써요: 모르는 ID는 열린 방이라 테스트마다 새 방을
 * 써서 서로 섞이지 않아요.
 */
@SpringBootTest
@AutoConfigureMockMvc
@Import({TestcontainersConfiguration.class, ChatApiTest.FakeRooms.class})
class ChatApiTest {

  static final LocalDate TODAY = LocalDate.now(ZoneId.of("Asia/Seoul"));

  /** 없는 공고 */
  static final UUID UNKNOWN = UUID.randomUUID();

  /** 접수 마감 31일이 지난 공고 → 오늘부터 읽기 전용 */
  static final UUID CLOSED = UUID.randomUUID();

  /** MERGED_INTO에 합쳐진 공고 */
  static final UUID MERGED = UUID.randomUUID();

  static final UUID MERGED_INTO = UUID.randomUUID();

  /** 상시 공고 (마감일 없음) */
  static final UUID ALWAYS = UUID.randomUUID();

  @TestConfiguration
  static class FakeRooms {
    @Bean
    @Primary
    ChatRooms fakeRooms() {
      return id -> {
        if (id.equals(UNKNOWN)) {
          return Optional.empty();
        }
        if (id.equals(CLOSED)) {
          return Optional.of(new ChatRoom(CLOSED, TODAY.minusDays(31)));
        }
        if (id.equals(MERGED) || id.equals(MERGED_INTO)) {
          return Optional.of(new ChatRoom(MERGED_INTO, TODAY.plusDays(10), List.of(MERGED)));
        }
        if (id.equals(ALWAYS)) {
          return Optional.of(new ChatRoom(ALWAYS, null));
        }
        return Optional.of(new ChatRoom(id, TODAY.plusDays(10)));
      };
    }
  }

  @Autowired MockMvc mvc;
  @Autowired SocialLoginService logins;
  @Autowired AuthTokenService tokens;
  @Autowired JdbcTemplate jdbc;
  @Autowired ApplicationEventPublisher events;

  @Test
  void readsWithoutLoginButWritesNeedLogin() throws Exception {
    UUID room = UUID.randomUUID();

    mvc.perform(get("/api/v1/notices/{id}/chat", room))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.noticeId").value(room.toString()))
        .andExpect(jsonPath("$.readOnly").value(false))
        .andExpect(jsonPath("$.readOnlyFrom").value(TODAY.plusDays(41).toString()))
        .andExpect(jsonPath("$.guide").isNotEmpty());
    mvc.perform(get("/api/v1/notices/{id}/chat/messages", room))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.items").isEmpty())
        .andExpect(jsonPath("$.hasNext").value(false));

    mvc.perform(
            post("/api/v1/notices/{id}/chat/messages", room)
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"content\": \"안녕하세요\"}"))
        .andExpect(status().isUnauthorized())
        .andExpect(jsonPath("$.code").value("UNAUTHENTICATED"));
    mvc.perform(put("/api/v1/chat/messages/{id}/like", UUID.randomUUID()))
        .andExpect(status().isUnauthorized());
  }

  @Test
  void sendThenListNewestFirstWithCursor() throws Exception {
    UUID room = UUID.randomUUID();
    LoginUser a = member();

    mvc.perform(
            post("/api/v1/notices/{id}/chat/messages", room)
                .header("Authorization", bearer(a))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"content\": \"  첫 번째  \"}"))
        .andExpect(status().isCreated())
        .andExpect(jsonPath("$.noticeId").value(room.toString()))
        .andExpect(jsonPath("$.content").value("첫 번째"))
        .andExpect(jsonPath("$.authorNickname").value(a.nickname()))
        .andExpect(jsonPath("$.status").value("VISIBLE"))
        .andExpect(jsonPath("$.likeCount").value(0))
        .andExpect(jsonPath("$.mine").value(true))
        .andExpect(jsonPath("$.parent").doesNotExist());
    send(room, a, "두 번째");
    send(room, a, "세 번째");

    MvcResult first =
        mvc.perform(
                get("/api/v1/notices/{id}/chat/messages", room)
                    .param("size", "2")
                    .header("Authorization", bearer(a)))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.items.length()").value(2))
            .andExpect(jsonPath("$.items[0].content").value("세 번째"))
            .andExpect(jsonPath("$.items[0].mine").value(true))
            .andExpect(jsonPath("$.hasNext").value(true))
            .andReturn();
    String next = JsonPath.read(body(first), "$.nextCursor");

    // 비로그인은 내 글 여부가 false
    mvc.perform(
            get("/api/v1/notices/{id}/chat/messages", room)
                .param("size", "2")
                .param("cursor", next))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.items.length()").value(1))
        .andExpect(jsonPath("$.items[0].content").value("첫 번째"))
        .andExpect(jsonPath("$.items[0].mine").value(false))
        .andExpect(jsonPath("$.hasNext").value(false));
    mvc.perform(get("/api/v1/notices/{id}/chat/messages", room).param("cursor", "broken"))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("INVALID_CURSOR"));
  }

  @Test
  void contentMustBe1To500Chars() throws Exception {
    UUID room = UUID.randomUUID();
    LoginUser a = member();

    sendRaw(room, a, "{\"content\": \"   \"}")
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("CHAT_INVALID_CONTENT"));
    sendRaw(room, a, "{}").andExpect(jsonPath("$.code").value("CHAT_INVALID_CONTENT"));
    sendRaw(room, a, "{\"content\": \"" + "가".repeat(501) + "\"}")
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("CHAT_INVALID_CONTENT"));
    // 이모지도 한 글자
    sendRaw(room, a, "{\"content\": \"" + "😀".repeat(500) + "\"}").andExpect(status().isCreated());
  }

  @Test
  void replyOnlyOneLevelInTheSameRoom() throws Exception {
    UUID room = UUID.randomUUID();
    LoginUser a = member();
    LoginUser b = member();
    String root = send(room, a, "버팀목 대출 같이 받을 수 있나요?");

    MvcResult reply =
        sendRaw(room, b, "{\"content\": \"네 저는 받았어요\", \"parentId\": \"" + root + "\"}")
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.parent.id").value(root))
            .andExpect(jsonPath("$.parent.authorNickname").value(a.nickname()))
            .andExpect(jsonPath("$.parent.content").value("버팀목 대출 같이 받을 수 있나요?"))
            .andReturn();
    String replyId = JsonPath.read(body(reply), "$.id");

    sendRaw(room, a, "{\"content\": \"감사해요\", \"parentId\": \"" + replyId + "\"}")
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("CHAT_REPLY_DEPTH"));
    sendRaw(UUID.randomUUID(), a, "{\"content\": \"다른 방\", \"parentId\": \"" + root + "\"}")
        .andExpect(status().isNotFound())
        .andExpect(jsonPath("$.code").value("CHAT_MESSAGE_NOT_FOUND"));
  }

  @Test
  void sixthMessageInAMinuteIs429WithRetryAfter() throws Exception {
    UUID room = UUID.randomUUID();
    LoginUser a = member();
    for (int i = 1; i <= 5; i++) {
      send(room, a, "메시지 " + i);
    }

    MvcResult limited =
        sendRaw(room, a, "{\"content\": \"여섯 번째\"}")
            .andExpect(status().isTooManyRequests())
            .andExpect(jsonPath("$.code").value("CHAT_RATE_LIMITED"))
            .andExpect(header().exists("Retry-After"))
            .andReturn();
    int retryAfter = Integer.parseInt(limited.getResponse().getHeader("Retry-After"));
    assertThat(retryAfter).isBetween(1, 60);
    // 다른 회원은 막히지 않아요
    send(room, member(), "저는 처음이에요");
  }

  @Test
  void readOnlyRoomBlocksSendAndLikeButAllowsReportAndDelete() throws Exception {
    LoginUser a = member();
    LoginUser b = member();
    mvc.perform(get("/api/v1/notices/{id}/chat", CLOSED))
        .andExpect(jsonPath("$.readOnly").value(true))
        .andExpect(jsonPath("$.readOnlyFrom").value(TODAY.toString()));
    sendRaw(CLOSED, a, "{\"content\": \"늦었나요?\"}")
        .andExpect(status().isConflict())
        .andExpect(jsonPath("$.code").value("CHAT_READ_ONLY"));

    // 마감 전에 쓴 메시지 (보내기는 막혀서 바로 저장해요)
    UUID old = UUID.randomUUID();
    jdbc.update(
        """
        insert into chat.messages (id, notice_id, user_id, author_nickname, content, status, created_at)
        values (?, ?, ?, ?, '010-1234-5678로 연락 주세요', 'VISIBLE', ?)
        """,
        old,
        CLOSED,
        a.userId(),
        a.nickname(),
        OffsetDateTime.now().minusDays(40));

    mvc.perform(put("/api/v1/chat/messages/{id}/like", old).header("Authorization", bearer(b)))
        .andExpect(status().isConflict())
        .andExpect(jsonPath("$.code").value("CHAT_READ_ONLY"));
    report(old, b, "PRIVACY").andExpect(status().isCreated());
    mvc.perform(delete("/api/v1/chat/messages/{id}", old).header("Authorization", bearer(a)))
        .andExpect(status().isNoContent());
  }

  @Test
  void alwaysOpenNoticeNeverBecomesReadOnly() throws Exception {
    mvc.perform(get("/api/v1/notices/{id}/chat", ALWAYS))
        .andExpect(jsonPath("$.readOnly").value(false))
        .andExpect(jsonPath("$.readOnlyFrom").doesNotExist());
  }

  @Test
  void onlyAuthorDeletesSoftlyAndAdminStillSeesReportedContent() throws Exception {
    UUID room = UUID.randomUUID();
    LoginUser a = member();
    String id = send(room, a, "욕설이 섞인 부적절한 글");
    report(id, member(), "ABUSE").andExpect(status().isCreated());

    mvc.perform(delete("/api/v1/chat/messages/{id}", id).header("Authorization", bearer(member())))
        .andExpect(status().isForbidden())
        .andExpect(jsonPath("$.code").value("CHAT_NOT_OWNER"));
    mvc.perform(delete("/api/v1/chat/messages/{id}", id).header("Authorization", bearer(a)))
        .andExpect(status().isNoContent());
    mvc.perform(delete("/api/v1/chat/messages/{id}", id).header("Authorization", bearer(a)))
        .andExpect(status().isNoContent());

    // 화면에서는 내려가요
    mvc.perform(get("/api/v1/notices/{id}/chat/messages", room))
        .andExpect(jsonPath("$.items[0].status").value("DELETED"))
        .andExpect(jsonPath("$.items[0].content").doesNotExist());
    // 소프트 삭제라 본문은 DB에 남고, 신고된 글이면 관리자가 지운 뒤에도 내용을 봐요
    assertThat(
            jdbc.queryForObject(
                "select content from chat.messages where id = ?::uuid", String.class, id))
        .isEqualTo("욕설이 섞인 부적절한 글");
    LoginUser admin = chatAdmin();
    MvcResult reports =
        mvc.perform(
                get("/api/admin/chat/reports")
                    .param("size", "100")
                    .header("Authorization", bearer(admin)))
            .andExpect(status().isOk())
            .andReturn();
    List<String> seen =
        JsonPath.read(body(reports), "$.items[?(@.messageId == '" + id + "')].message.content");
    assertThat(seen).containsExactly("욕설이 섞인 부적절한 글");

    // 지운 글의 신고도 관리자가 닫을 수 있어요. 지운 글은 다시 보이게 하지 않아요
    review(id, admin, "KEEP_HIDDEN");
    assertThat(
            jdbc.queryForList(
                "select review_status from chat.message_reports where message_id = ?::uuid",
                String.class,
                id))
        .containsOnly("KEPT_HIDDEN");
    // 누가 처리했는지 남아요 (관리자 처리 기록)
    assertThat(
            jdbc.queryForList(
                "select reviewed_by from chat.message_reports where message_id = ?::uuid",
                UUID.class,
                id))
        .containsOnly(admin.userId());
    review(id, admin, "RESTORE");
    assertThat(
            jdbc.queryForObject(
                "select status from chat.messages where id = ?::uuid", String.class, id))
        .isEqualTo("DELETED");
  }

  @Test
  void likeAndUnlikeAreIdempotent() throws Exception {
    UUID room = UUID.randomUUID();
    String id = send(room, member(), "좋아요 눌러 주세요");
    LoginUser b = member();

    for (int i = 0; i < 2; i++) {
      mvc.perform(put("/api/v1/chat/messages/{id}/like", id).header("Authorization", bearer(b)))
          .andExpect(status().isOk())
          .andExpect(jsonPath("$.likeCount").value(1))
          .andExpect(jsonPath("$.liked").value(true));
    }
    mvc.perform(get("/api/v1/notices/{id}/chat/messages", room).header("Authorization", bearer(b)))
        .andExpect(jsonPath("$.items[0].likeCount").value(1))
        .andExpect(jsonPath("$.items[0].likedByMe").value(true));
    for (int i = 0; i < 2; i++) {
      mvc.perform(delete("/api/v1/chat/messages/{id}/like", id).header("Authorization", bearer(b)))
          .andExpect(status().isOk())
          .andExpect(jsonPath("$.likeCount").value(0))
          .andExpect(jsonPath("$.liked").value(false));
    }
  }

  @Test
  void thirdReportHidesUntilAdminRestores() throws Exception {
    UUID room = UUID.randomUUID();
    String id = send(room, member(), "광고 링크 http://example.com");
    LoginUser b = member();

    report(id, b, "AD").andExpect(status().isCreated());
    report(id, member(), "AD").andExpect(status().isCreated());
    messageAt(room).andExpect(jsonPath("$.items[0].status").value("VISIBLE"));
    report(id, member(), "ABUSE").andExpect(status().isCreated());
    messageAt(room)
        .andExpect(jsonPath("$.items[0].status").value("HIDDEN_REPORTED"))
        .andExpect(jsonPath("$.items[0].content").doesNotExist());

    report(id, b, "AD")
        .andExpect(status().isConflict())
        .andExpect(jsonPath("$.code").value("CHAT_ALREADY_REPORTED"));
    mvc.perform(
            post("/api/v1/chat/messages/{id}/reports", id)
                .header("Authorization", bearer(b))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"reason\": \"ETC\", \"detail\": \"" + "가".repeat(201) + "\"}"))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"));

    // 관리자만 신고 목록을 봐요
    LoginUser user = member();
    LoginUser admin = chatAdmin();
    mvc.perform(get("/api/admin/chat/reports").header("Authorization", bearer(user)))
        .andExpect(status().isForbidden());
    MvcResult pending =
        mvc.perform(
                get("/api/admin/chat/reports")
                    .param("size", "100")
                    .header("Authorization", bearer(admin)))
            .andExpect(status().isOk())
            .andReturn();
    List<String> contents =
        JsonPath.read(body(pending), "$.items[?(@.messageId == '" + id + "')].message.content");
    assertThat(contents).hasSize(3).allMatch(c -> c.equals("광고 링크 http://example.com"));
    // 사이드바 숫자: 신고 3건이 걸린 글은 한 글로 세요
    Integer pendingMessages =
        jdbc.queryForObject(
            "select count(distinct message_id) from chat.message_reports where review_status = 'PENDING'",
            Integer.class);
    mvc.perform(get("/api/admin/chat/reports/counts").header("Authorization", bearer(admin)))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.pendingMessages").value(pendingMessages));

    review(id, admin, "RESTORE");
    messageAt(room)
        .andExpect(jsonPath("$.items[0].status").value("VISIBLE"))
        .andExpect(jsonPath("$.items[0].content").value("광고 링크 http://example.com"));
    assertThat(
            jdbc.queryForList(
                "select review_status from chat.message_reports where message_id = ?::uuid",
                String.class,
                id))
        .containsOnly("RESTORED");
    // 되돌린 뒤에는 새 신고 3건이 쌓여야 다시 가려져요
    report(id, member(), "AD").andExpect(status().isCreated());
    messageAt(room).andExpect(jsonPath("$.items[0].status").value("VISIBLE"));

    review(id, admin, "KEEP_HIDDEN");
    messageAt(room).andExpect(jsonPath("$.items[0].status").value("HIDDEN_ADMIN"));
  }

  @Test
  void mergedNoticeUsesTheSurvivingRoomAndUnknownIs404() throws Exception {
    LoginUser a = member();
    mvc.perform(get("/api/v1/notices/{id}/chat", MERGED))
        .andExpect(jsonPath("$.noticeId").value(MERGED_INTO.toString()));
    sendRaw(MERGED, a, "{\"content\": \"합쳐진 공고에서 보냄\"}")
        .andExpect(status().isCreated())
        .andExpect(jsonPath("$.noticeId").value(MERGED_INTO.toString()));
    mvc.perform(get("/api/v1/notices/{id}/chat/messages", MERGED_INTO))
        .andExpect(jsonPath("$.items[0].content").value("합쳐진 공고에서 보냄"));

    // 2026-11-10 코드 검토: 합치기 전에 합쳐진 공고에 쓴 메시지도 남은 방 목록에 보이고 답장할 수 있어요(예전엔 사라짐)
    UUID before = UUID.randomUUID();
    jdbc.update(
        """
        insert into chat.messages (id, notice_id, user_id, author_nickname, content, status, created_at)
        values (?, ?, ?, ?, '합치기 전 메시지', 'VISIBLE', ?)
        """,
        before,
        MERGED,
        a.userId(),
        a.nickname(),
        OffsetDateTime.now().minusDays(1));
    mvc.perform(get("/api/v1/notices/{id}/chat/messages", MERGED_INTO))
        .andExpect(jsonPath("$.items[?(@.content == '합치기 전 메시지')]").exists());
    sendRaw(MERGED_INTO, a, "{\"content\": \"답장\", \"parentId\": \"" + before + "\"}")
        .andExpect(status().isCreated());

    mvc.perform(get("/api/v1/notices/{id}/chat", UNKNOWN))
        .andExpect(status().isNotFound())
        .andExpect(jsonPath("$.code").value("NOTICE_NOT_FOUND"));
    sendRaw(UNKNOWN, a, "{\"content\": \"없는 공고\"}").andExpect(status().isNotFound());
  }

  @Test
  void streamSendsCommittedMessagesAndResumesAfterLastEventId() throws Exception {
    UUID room = UUID.randomUUID();
    LoginUser a = member();
    String first = send(room, a, "첫 메시지");

    MvcResult stream =
        mvc.perform(get("/api/v1/notices/{id}/chat/stream", room))
            .andExpect(request().asyncStarted())
            .andReturn();
    assertThat(stream.getResponse().getContentType()).startsWith("text/event-stream");
    String second = send(room, a, "두 번째 메시지");
    mvc.perform(
            put("/api/v1/chat/messages/{id}/like", second)
                .header("Authorization", bearer(member())))
        .andExpect(status().isOk());

    String events = body(stream);
    assertThat(events)
        .contains(":connected")
        .contains("event:message.created")
        .contains("id:" + second)
        .contains("두 번째 메시지")
        .contains("event:like.updated")
        .doesNotContain("id:" + first);

    // 재연결: Last-Event-ID 뒤 메시지를 먼저 받아요
    MvcResult resumed =
        mvc.perform(get("/api/v1/notices/{id}/chat/stream", room).header("Last-Event-ID", first))
            .andExpect(request().asyncStarted())
            .andReturn();
    assertThat(body(resumed)).contains("id:" + second).doesNotContain("id:" + first);

    // 실패한 보내기는 SSE로 나가지 않아요 (첫 연결이 받은 message.created는 두 번째 메시지 하나뿐)
    sendRaw(room, a, "{\"content\": \"\"}").andExpect(status().isBadRequest());
    assertThat(body(stream).split("event:message.created", -1)).hasSize(2);
  }

  @Test
  void withdrawalDeletesTheMembersRowsButKeepsOthersReplies() throws Exception {
    UUID room = UUID.randomUUID();
    LoginUser a = member();
    LoginUser b = member();
    String mine = send(room, a, "탈퇴할 회원의 글");
    MvcResult reply =
        sendRaw(room, b, "{\"content\": \"남는 회원의 답장\", \"parentId\": \"" + mine + "\"}")
            .andExpect(status().isCreated())
            .andReturn();
    String replyId = JsonPath.read(body(reply), "$.id");
    mvc.perform(put("/api/v1/chat/messages/{id}/like", mine).header("Authorization", bearer(b)))
        .andExpect(status().isOk());
    mvc.perform(put("/api/v1/chat/messages/{id}/like", replyId).header("Authorization", bearer(a)))
        .andExpect(jsonPath("$.likeCount").value(1));
    report(replyId, a, "ETC").andExpect(status().isCreated());
    MvcResult stream =
        mvc.perform(get("/api/v1/notices/{id}/chat/stream", room))
            .andExpect(request().asyncStarted())
            .andReturn();

    // user 모듈이 탈퇴를 커밋하면 이 이벤트가 나가요 (테스트는 트랜잭션 밖에서 바로 보냄)
    events.publishEvent(new UserWithdrawn(a.userId()));

    // 그 회원의 메시지·좋아요·신고 줄이 남지 않아요 (다른 모듈 제보처럼)
    for (String sql :
        List.of(
            "select count(*) from chat.messages where user_id = ?",
            "select count(*) from chat.message_likes where user_id = ?",
            "select count(*) from chat.message_reports where reporter_id = ?")) {
      assertThat(jdbc.queryForObject(sql, Integer.class, a.userId())).as(sql).isZero();
    }
    // 지운 메시지에 다른 사람이 누른 좋아요도 같이 지워져요
    assertThat(
            jdbc.queryForObject(
                "select count(*) from chat.message_likes where message_id = ?::uuid",
                Integer.class,
                mine))
        .isZero();
    // 남는 답장의 좋아요·검토 전 신고 수는 그 회원 몫만큼 줄어요
    var counts =
        jdbc.queryForMap(
            "select like_count, report_count from chat.messages where id = ?::uuid", replyId);
    assertThat(counts.get("like_count")).isEqualTo(0);
    assertThat(counts.get("report_count")).isEqualTo(0);
    // 다른 사람의 답장은 남고, 원문 자리는 지운 글처럼 보여요
    mvc.perform(get("/api/v1/notices/{id}/chat/messages", room))
        .andExpect(jsonPath("$.items.length()").value(1))
        .andExpect(jsonPath("$.items[0].id").value(replyId))
        .andExpect(jsonPath("$.items[0].parent.id").value(mine))
        .andExpect(jsonPath("$.items[0].parent.status").value("DELETED"))
        .andExpect(jsonPath("$.items[0].parent.content").doesNotExist())
        .andExpect(jsonPath("$.items[0].parent.authorNickname").doesNotExist());
    // 보고 있던 사람 화면에서도 내려가요
    assertThat(body(stream)).contains("event:message.deleted").contains(mine);
  }

  @Test
  void mobileAndResidentNumbersCannotBePosted() throws Exception {
    UUID room = UUID.randomUUID();
    LoginUser a = member();

    for (String content : List.of("연락 주세요 010-1234-5678", "01012345678", "주민번호 970101-1234567")) {
      sendRaw(room, a, "{\"content\": \"" + content + "\"}")
          .andExpect(status().isBadRequest())
          .andExpect(jsonPath("$.code").value("CHAT_PERSONAL_INFO"))
          .andExpect(jsonPath("$.detail").value(not(containsString("1234"))));
    }
    assertThat(
            jdbc.queryForObject(
                "select count(*) from chat.messages where notice_id = ?", Integer.class, room))
        .isZero();
    // 대표번호는 막지 않아요
    send(room, a, "LH 콜센터 1600-1004로 물어보세요");
  }

  private LoginUser member() {
    String id = UUID.randomUUID().toString();
    return logins.login(new SocialProfile(SocialProvider.KAKAO, id, "회원" + id.substring(0, 6)));
  }

  /** 채팅 신고를 검토할 수 있는 관리자 (관리자 화면 권한은 요청마다 DB로 확인해서 DB에 관리자·「채팅 제재」를 넣어요) */
  private LoginUser chatAdmin() {
    LoginUser m = member();
    jdbc.update("update account.users set role = 'ADMIN' where id = ?", m.userId());
    jdbc.update(
        "insert into account.admin_permissions (user_id, permission) values (?, 'CHAT')",
        m.userId());
    return new LoginUser(m.userId(), m.nickname(), "ADMIN");
  }

  private String bearer(LoginUser user) {
    return "Bearer " + tokens.issue(user).accessToken();
  }

  private org.springframework.test.web.servlet.ResultActions sendRaw(
      UUID room, LoginUser user, String json) throws Exception {
    return mvc.perform(
        post("/api/v1/notices/{id}/chat/messages", room)
            .header("Authorization", bearer(user))
            .contentType(MediaType.APPLICATION_JSON)
            .content(json));
  }

  /** 보내고 메시지 ID를 돌려줘요. */
  private String send(UUID room, LoginUser user, String content) throws Exception {
    MvcResult result =
        sendRaw(room, user, "{\"content\": \"" + content + "\"}")
            .andExpect(status().isCreated())
            .andReturn();
    return JsonPath.read(body(result), "$.id");
  }

  private org.springframework.test.web.servlet.ResultActions report(
      String messageId, LoginUser user, String reason) throws Exception {
    return mvc.perform(
        post("/api/v1/chat/messages/{id}/reports", messageId)
            .header("Authorization", bearer(user))
            .contentType(MediaType.APPLICATION_JSON)
            .content("{\"reason\": \"" + reason + "\"}"));
  }

  private org.springframework.test.web.servlet.ResultActions report(
      UUID messageId, LoginUser user, String reason) throws Exception {
    return report(messageId.toString(), user, reason);
  }

  private void review(String messageId, LoginUser admin, String action) throws Exception {
    mvc.perform(
            patch("/api/admin/chat/messages/{id}", messageId)
                .header("Authorization", bearer(admin))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"action\": \"" + action + "\"}"))
        .andExpect(status().isNoContent());
  }

  /** 방의 최신 메시지 목록 (비로그인). */
  private org.springframework.test.web.servlet.ResultActions messageAt(UUID room) throws Exception {
    return mvc.perform(get("/api/v1/notices/{id}/chat/messages", room)).andExpect(status().isOk());
  }

  private static String body(MvcResult result) throws Exception {
    return result.getResponse().getContentAsString(StandardCharsets.UTF_8);
  }
}
