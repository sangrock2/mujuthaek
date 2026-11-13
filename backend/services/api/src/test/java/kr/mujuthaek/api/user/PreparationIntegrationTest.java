package kr.mujuthaek.api.user;

import static org.assertj.core.api.Assertions.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

import java.nio.charset.StandardCharsets;
import java.util.UUID;
import java.util.concurrent.Executors;
import kr.mujuthaek.api.TestcontainersConfiguration;
import kr.mujuthaek.api.common.exception.CustomException;
import kr.mujuthaek.api.common.exception.ErrorCode;
import kr.mujuthaek.api.notice.service.internal.NoticeIngestionService;
import kr.mujuthaek.api.notice.service.internal.NoticeMergeService;
import kr.mujuthaek.api.user.domain.SocialProvider;
import kr.mujuthaek.api.user.service.*;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.test.web.servlet.MockMvc;
import tools.jackson.databind.json.JsonMapper;
import tools.jackson.databind.node.ObjectNode;

@SpringBootTest(
    properties = {
      "spring.rabbitmq.listener.simple.auto-startup=false",
      "notification.deadline-reminder.enabled=false",
      "notice.status-refresh.enabled=false",
      "mujuthaek.judging.prewarm=false"
    })
@AutoConfigureMockMvc
@Import(TestcontainersConfiguration.class)
class PreparationIntegrationTest {
  @Autowired PreparationService service;
  @Autowired SocialLoginService login;
  @Autowired AuthTokenService tokens;
  @Autowired FavoriteService favorites;
  @Autowired NoticeIngestionService ingestion;
  @Autowired NoticeMergeService merges;
  @Autowired JdbcClient jdbc;
  @Autowired JsonMapper json;
  @Autowired MockMvc mvc;
  LoginUser user;
  UUID noticeId;
  ObjectNode event;

  @BeforeEach
  void setUp() throws Exception {
    jdbc.sql(
            "truncate account.users, notice.notices, notice.extraction_results, common.processed_events cascade")
        .update();
    user = login.login(new SocialProfile(SocialProvider.KAKAO, "preparation-test", "준비 테스트"));
    try (var in = getClass().getResourceAsStream("/contracts/examples/extraction.completed.json")) {
      event = (ObjectNode) json.readTree(new String(in.readAllBytes(), StandardCharsets.UTF_8));
    }
    var doc = (ObjectNode) event.path("payload").path("notice").path("requiredDocuments").get(0);
    doc.put("group", "COMMON");
    doc.put("appliesTo", "신청자");
    assertThat(ingestion.apply(event.toString()).name()).isEqualTo("PUBLISHED");
    noticeId =
        jdbc.sql("select id from notice.notices where not hidden").query(UUID.class).single();
  }

  @Test
  void createIsIdempotentAndFavoritesAndPreparationAreIndependent() {
    var result = service.create(user.userId(), noticeId);
    var p = result.preparation();
    assertThat(result.created()).isTrue();
    assertThat(p.favorite()).isTrue();
    assertThat(p.documents()).hasSize(1);
    assertThat(p.progress().total()).isEqualTo(1);
    assertThat(p.documents().getFirst().state()).isEqualTo("TODO");
    assertThat(service.create(user.userId(), noticeId).created()).isFalse();
    assertThat(service.list(user.userId(), null, null, 100).items()).hasSize(1);
    favorites.remove(user.userId(), "NOTICE", noticeId);
    assertThat(service.get(user.userId(), p.id()).favorite()).isFalse();
    assertThat(service.create(user.userId(), noticeId).preparation().favorite()).isFalse();
    favorites.add(user.userId(), "NOTICE", noticeId);
    service.delete(user.userId(), p.id());
    assertThat(favorites.list(user.userId(), null, null, 100).items()).hasSize(1);
    service.delete(user.userId(), p.id());
  }

  @Test
  void optimisticUpdatesArchiveRestoreAndAcknowledgementAreSeparate() {
    var p = service.create(user.userId(), noticeId).preparation();
    var done =
        service.document(
            user.userId(),
            p.id(),
            p.documents().getFirst().source().path("id").asString(),
            "DONE",
            p.sourceRevision(),
            p.revision());
    assertThat(done.progress().done()).isEqualTo(1);
    assertThatThrownBy(
            () -> service.change(user.userId(), p.id(), "SUBMITTED", false, p.revision()))
        .isInstanceOf(CustomException.class);
    var submitted = service.change(user.userId(), p.id(), "SUBMITTED", false, done.revision());
    assertThat(submitted.submittedAt()).isNotNull();
    var archived = service.change(user.userId(), p.id(), "ARCHIVED", false, submitted.revision());
    var restored = service.change(user.userId(), p.id(), null, true, archived.revision());
    assertThat(restored.status()).isEqualTo("SUBMITTED");
    assertThat(
            service
                .change(user.userId(), p.id(), "PREPARING", false, restored.revision())
                .submittedAt())
        .isNull();
    var fresh = service.get(user.userId(), p.id());
    assertThatThrownBy(
            () -> service.acknowledge(user.userId(), p.id(), "old-source", fresh.revision()))
        .isInstanceOf(CustomException.class);
  }

  @Test
  void correctedDocumentRequiresRecheckAndStaleWriteIsRejected() {
    var p = service.create(user.userId(), noticeId).preparation();
    String docId = p.documents().getFirst().source().path("id").asString();
    p = service.document(user.userId(), p.id(), docId, "DONE", p.sourceRevision(), p.revision());
    correctDocument("신분증");
    var changed = service.get(user.userId(), p.id());
    assertThat(changed.needsReview()).isTrue();
    assertThat(changed.progress().done()).isZero();
    assertThat(changed.documents().getFirst().state()).isEqualTo("RECHECK_REQUIRED");
    var acknowledged =
        service.acknowledge(user.userId(), p.id(), changed.sourceRevision(), changed.revision());
    assertThat(acknowledged.documents().getFirst().state()).isEqualTo("RECHECK_REQUIRED");
    assertThat(acknowledged.reviewReasons()).contains("DOCUMENT_RECHECK");
    var done =
        service.document(
            user.userId(),
            p.id(),
            docId,
            "DONE",
            acknowledged.sourceRevision(),
            acknowledged.revision());
    assertThat(done.needsReview()).isFalse();
    var old = p;
    assertThatThrownBy(
            () ->
                service.document(
                    user.userId(), old.id(), docId, "DONE", old.sourceRevision(), old.revision()))
        .isInstanceOf(CustomException.class);
  }

  @Test
  void followUpChangesWithoutNoticeVersionAndHiddenContentIsPurged() {
    var p = service.create(user.userId(), noticeId).preparation();
    jdbc.sql(
            "insert into notice.notice_follow_ups(raw_post_id,notice_id,original_notice_id,raw_version,source_event_id,title,detail_url,schedules,content_hash,review_status,created_at,updated_at) values(:raw,:notice,:notice,1,:event,'후속 안내','https://example.org','[]'::jsonb,'test','APPROVED',now(),now())")
        .param("raw", UUID.randomUUID())
        .param("notice", noticeId)
        .param("event", UUID.randomUUID())
        .update();
    var changed = service.get(user.userId(), p.id());
    assertThat(changed.reviewReasons()).contains("followUps");
    jdbc.sql("update notice.notices set hidden=true where id=:id").param("id", noticeId).update();
    var hidden = service.get(user.userId(), p.id());
    assertThat(hidden.source().isEmpty()).isTrue();
    assertThat(hidden.documents()).isEmpty();
    assertThat(hidden.reviewReasons()).contains("SOURCE_UNAVAILABLE");
    assertThat(
            jdbc.sql(
                    "select acknowledged_snapshot::text from account.application_preparations where id=:id")
                .param("id", p.id())
                .query(String.class)
                .single())
        .isEqualTo("{}");
  }

  @Test
  void actualHttpAuthenticationOwnershipValidationAndCascade() throws Exception {
    var p = service.create(user.userId(), noticeId).preparation();
    mvc.perform(get("/api/users/me/preparations")).andExpect(status().isUnauthorized());
    String bearer = "Bearer " + tokens.issue(user).accessToken();
    mvc.perform(get("/api/users/me/preparations/" + p.id()).header("Authorization", bearer))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.noticeId").value(noticeId.toString()));
    mvc.perform(
            patch("/api/users/me/preparations/" + p.id())
                .header("Authorization", bearer)
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"status\":\"SUBMITTED\"}"))
        .andExpect(status().isBadRequest());
    var other = login.login(new SocialProfile(SocialProvider.KAKAO, "other", "다른 회원"));
    String token = "Bearer " + tokens.issue(other).accessToken();
    mvc.perform(get("/api/users/me/preparations/" + p.id()).header("Authorization", token))
        .andExpect(status().isNotFound());
    mvc.perform(
            patch("/api/users/me/preparations/" + p.id())
                .header("Authorization", token)
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"status\":\"SUBMITTED\",\"expectedRevision\":0}"))
        .andExpect(status().isNotFound());
    jdbc.sql("delete from account.users where id=:id").param("id", user.userId()).update();
    assertThat(
            jdbc.sql("select count(*) from account.application_preparations")
                .query(Long.class)
                .single())
        .isZero();
    assertThat(
            jdbc.sql("select count(*) from account.application_preparation_documents")
                .query(Long.class)
                .single())
        .isZero();
  }

  @Test
  void concurrentCreationAndDocumentWritesAreSerialized() throws Exception {
    try (var pool = Executors.newVirtualThreadPerTaskExecutor()) {
      var futures =
          java.util.stream.IntStream.range(0, 8)
              .mapToObj(
                  i ->
                      pool.submit(() -> service.create(user.userId(), noticeId).preparation().id()))
              .toList();
      var ids = new java.util.HashSet<UUID>();
      for (var f : futures) ids.add(f.get());
      assertThat(ids).hasSize(1);
    }
  }

  private void correctDocument(String name) {
    event.put("eventId", UUID.randomUUID().toString());
    ((ObjectNode) event.path("payload")).put("rawVersion", 2);
    ((ObjectNode) event.path("payload").path("notice").path("input")).put("rawVersion", 2);
    ((ObjectNode) event.path("payload").path("notice").path("sourceReferences").get(0))
        .put("rawVersion", 2);
    ((ObjectNode) event.path("payload").path("notice").path("requiredDocuments").get(0))
        .put("name", name);
    assertThat(ingestion.apply(event.toString()).name()).isEqualTo("NEW_VERSION");
  }

  @Test
  void limitsRollbackBothRecordsAndUnsupportedFieldsAreRejected() {
    jdbc.sql(
            "insert into account.favorites(user_id,target_type,target_id,created_at) select :user,'NOTICE',gen_random_uuid(),now() from generate_series(1,200)")
        .param("user", user.userId())
        .update();
    assertThatThrownBy(() -> service.create(user.userId(), noticeId))
        .isInstanceOfSatisfying(
            CustomException.class,
            e -> assertThat(e.errorCode()).isEqualTo(ErrorCode.FAVORITE_LIMIT_EXCEEDED));
    assertThat(
            jdbc.sql("select count(*) from account.application_preparations")
                .query(Long.class)
                .single())
        .isZero();
    jdbc.sql("delete from account.favorites").update();
    jdbc.sql(
            "insert into account.application_preparations(id,user_id,notice_id,acknowledged_source_revision,source_revision,source_snapshot,acknowledged_snapshot,created_at,updated_at) select gen_random_uuid(),:user,gen_random_uuid(),'unavailable','unavailable','{}'::jsonb,'{}'::jsonb,now(),now() from generate_series(1,200)")
        .param("user", user.userId())
        .update();
    assertThatThrownBy(() -> service.create(user.userId(), noticeId))
        .isInstanceOfSatisfying(
            CustomException.class,
            e -> assertThat(e.errorCode()).isEqualTo(ErrorCode.PREPARATION_LIMIT_EXCEEDED));
    assertThat(favorites.list(user.userId(), null, null, 100).items()).isEmpty();
  }

  @Test
  void removedConditionalAndIncompleteDocumentsDoNotInheritCompletion() {
    var p = service.create(user.userId(), noticeId).preparation();
    var originalId = p.documents().getFirst().source().path("id").asString();
    p =
        service.document(
            user.userId(), p.id(), originalId, "NOT_APPLICABLE", p.sourceRevision(), p.revision());
    assertThat(p.progress().total()).isZero();
    var payload = (ObjectNode) event.path("payload").deepCopy();
    var doc = (ObjectNode) payload.path("notice").path("requiredDocuments").get(0);
    doc.put("id", "conditional").put("group", "CONDITIONAL");
    replacePayload(payload);
    var changed = service.get(user.userId(), p.id());
    assertThat(changed.removedDocuments()).hasSize(1);
    assertThat(changed.documents().getFirst().state()).isEqualTo("CHECK_REQUIRED");
    assertThatThrownBy(
            () ->
                service.document(
                    user.userId(),
                    changed.id(),
                    originalId,
                    "DONE",
                    changed.sourceRevision(),
                    changed.revision()))
        .isInstanceOf(CustomException.class);
    doc.putNull("id");
    replacePayload(payload);
    var incomplete = service.get(user.userId(), p.id());
    assertThat(incomplete.reviewReasons()).contains("SOURCE_INCOMPLETE");
    assertThat(incomplete.documents()).isEmpty();
  }

  @Test
  void mergedPreparationsResolveOldLinksAndRequireRecheck() {
    var first = service.create(user.userId(), noticeId).preparation();
    var another = (ObjectNode) event.deepCopy();
    UUID raw = UUID.randomUUID();
    another.put("eventId", UUID.randomUUID().toString());
    var p = (ObjectNode) another.path("payload");
    p.put("rawPostId", raw.toString()).put("title", "서로 다른 주거 공고");
    ((ObjectNode) p.path("notice").path("input")).put("rawPostId", raw.toString());
    ((ObjectNode) p.path("notice").path("sourceReferences").get(0))
        .put("rawPostId", raw.toString())
        .put("sourceNoticeId", "another");
    ((ObjectNode) p.path("notice").path("notice"))
        .put("title", "서로 다른 주거 공고")
        .put("announcedOn", "2026-12-01");
    ingestion.apply(another.toString());
    UUID secondNotice =
        jdbc.sql("select id from notice.notices where id<>:first and merged_into is null")
            .param("first", noticeId)
            .query(UUID.class)
            .single();
    var second = service.create(user.userId(), secondNotice).preparation();
    service.addTask(user.userId(), first.id(), "원래 공고의 할 일", null, first.revision());
    service.addTask(user.userId(), second.id(), "합쳐질 공고의 할 일", null, second.revision());
    merges.merge(secondNotice, noticeId);
    var list = service.list(user.userId(), null, null, 100);
    assertThat(list.items()).hasSize(1);
    assertThat(list.items().getFirst().tasks())
        .extracting(PreparationService.TaskView::title)
        .containsExactlyInAnyOrder("원래 공고의 할 일", "합쳐질 공고의 할 일");
    assertThat(list.items().getFirst().reviewReasons()).contains("NOTICE_MERGED");
    assertThat(service.get(user.userId(), second.id()).id()).isEqualTo(first.id());
    assertThat(service.get(user.userId(), second.id()).noticeId()).isEqualTo(noticeId);
  }

  @Test
  void invalidTransitionsAndCursorsAreRejected() {
    var p = service.create(user.userId(), noticeId).preparation();
    assertThatThrownBy(() -> service.change(user.userId(), p.id(), null, false, p.revision()))
        .isInstanceOf(CustomException.class);
    assertThatThrownBy(() -> service.change(user.userId(), p.id(), null, true, p.revision()))
        .isInstanceOf(CustomException.class);
    assertThatThrownBy(
            () ->
                service.document(
                    user.userId(),
                    p.id(),
                    "x",
                    "RECHECK_REQUIRED",
                    p.sourceRevision(),
                    p.revision()))
        .isInstanceOf(CustomException.class);
    assertThatThrownBy(() -> service.list(user.userId(), "INVALID", null, 10))
        .isInstanceOf(CustomException.class);
    assertThatThrownBy(() -> service.list(user.userId(), null, "invalid", 10))
        .isInstanceOf(CustomException.class);
    var archived = service.change(user.userId(), p.id(), "ARCHIVED", false, p.revision());
    assertThatThrownBy(
            () -> service.change(user.userId(), p.id(), "SUBMITTED", false, archived.revision()))
        .isInstanceOf(CustomException.class);
    assertThat(service.list(user.userId(), "PREPARING", null, 10).items()).isEmpty();
    assertThat(service.list(user.userId(), "ARCHIVED", null, 10).items()).hasSize(1);
  }

  private void replacePayload(ObjectNode payload) {
    jdbc.sql(
            "update notice.notice_versions set payload=cast(:payload as jsonb) where notice_id=:id and version=1")
        .param("payload", payload.toString())
        .param("id", noticeId)
        .update();
  }

  @Test
  void personalTasksPersistEditCompleteAndDeleteWithRevisionChecks() throws Exception {
    var p = service.create(user.userId(), noticeId).preparation();
    var withTask =
        service.addTask(
            user.userId(),
            p.id(),
            "  신청 사이트 가입하기  ",
            java.time.LocalDate.of(2026, 11, 15),
            p.revision());
    var task = withTask.tasks().getFirst();
    assertThat(task.title()).isEqualTo("신청 사이트 가입하기");
    assertThat(task.done()).isFalse();
    assertThat(service.get(user.userId(), p.id()).tasks()).hasSize(1);
    assertThat(service.list(user.userId(), null, null, 100).items().getFirst().tasks()).hasSize(1);
    assertThatThrownBy(
            () ->
                service.updateTask(
                    user.userId(), p.id(), task.id(), "변경", null, true, p.revision()))
        .isInstanceOfSatisfying(
            CustomException.class,
            e -> assertThat(e.errorCode()).isEqualTo(ErrorCode.PREPARATION_CONFLICT));
    var updated =
        service.updateTask(
            user.userId(), p.id(), task.id(), "인증까지 완료", null, true, withTask.revision());
    assertThat(updated.tasks().getFirst().done()).isTrue();
    assertThat(updated.tasks().getFirst().dueOn()).isNull();
    var reopened =
        service.updateTask(
            user.userId(), p.id(), task.id(), "다시 확인", null, false, updated.revision());
    assertThat(reopened.tasks().getFirst().done()).isFalse();
    String bearer = "Bearer " + tokens.issue(user).accessToken();
    mvc.perform(
            delete("/api/users/me/preparations/" + p.id() + "/tasks/" + task.id())
                .param("expectedRevision", Long.toString(reopened.revision()))
                .header("Authorization", bearer))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.tasks").isEmpty());
    assertThat(service.get(user.userId(), p.id()).tasks()).isEmpty();
  }

  @Test
  void personalTaskOwnershipValidationLimitAndCascade() throws Exception {
    var p = service.create(user.userId(), noticeId).preparation();
    String token = "Bearer " + tokens.issue(user).accessToken();
    mvc.perform(
            post("/api/users/me/preparations/" + p.id() + "/tasks")
                .header("Authorization", token)
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\" \",\"dueOn\":null,\"expectedRevision\":0}"))
        .andExpect(status().isBadRequest());
    var withTask = service.addTask(user.userId(), p.id(), "내가 정한 할 일", null, p.revision());
    var other = login.login(new SocialProfile(SocialProvider.KAKAO, "tasks-other", "다른 회원"));
    assertThatThrownBy(
            () ->
                service.updateTask(
                    other.userId(),
                    p.id(),
                    withTask.tasks().getFirst().id(),
                    "다른 회원 수정",
                    null,
                    true,
                    withTask.revision()))
        .isInstanceOfSatisfying(
            CustomException.class,
            e -> assertThat(e.errorCode()).isEqualTo(ErrorCode.PREPARATION_NOT_FOUND));
    var current = withTask;
    for (int i = 1; i < 30; i++)
      current = service.addTask(user.userId(), p.id(), "할 일 " + i, null, current.revision());
    long revision = current.revision();
    assertThatThrownBy(() -> service.addTask(user.userId(), p.id(), "31번째", null, revision))
        .isInstanceOfSatisfying(
            CustomException.class,
            e -> assertThat(e.errorCode()).isEqualTo(ErrorCode.PREPARATION_TASK_LIMIT_EXCEEDED));
    assertThatThrownBy(() -> service.deleteTask(user.userId(), p.id(), UUID.randomUUID(), revision))
        .isInstanceOfSatisfying(
            CustomException.class,
            e -> assertThat(e.errorCode()).isEqualTo(ErrorCode.PREPARATION_TASK_NOT_FOUND));
    service.delete(user.userId(), p.id());
    assertThat(
            jdbc.sql("select count(*) from account.application_preparation_tasks")
                .query(Long.class)
                .single())
        .isZero();
  }
}
