package kr.mujuthaek.api.user.repository;

import java.time.Instant;
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.Collection;
import java.util.List;
import java.util.UUID;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

@Repository
public class PreparationRepository {
  private final JdbcClient jdbc;
  private final JsonMapper json;

  public PreparationRepository(JdbcClient jdbc, JsonMapper json) {
    this.jdbc = jdbc;
    this.json = json;
  }

  public record Saved(
      UUID id,
      UUID userId,
      UUID noticeId,
      String status,
      String archivedFromStatus,
      Instant submittedAt,
      String acknowledgedSourceRevision,
      String sourceRevision,
      JsonNode sourceSnapshot,
      JsonNode acknowledgedSnapshot,
      long revision,
      boolean mergeReview,
      Instant createdAt,
      Instant updatedAt) {}

  public record Document(
      UUID preparationId, String id, String fingerprint, String state, boolean active) {}

  public List<Saved> list(UUID userId) {
    return jdbc.sql(
            "select * from account.application_preparations where user_id=:user order by created_at,id")
        .param("user", userId)
        .query(
            (rs, i) ->
                new Saved(
                    rs.getObject("id", UUID.class),
                    userId,
                    rs.getObject("notice_id", UUID.class),
                    rs.getString("status"),
                    rs.getString("archived_from_status"),
                    instant(rs.getObject("submitted_at", OffsetDateTime.class)),
                    rs.getString("acknowledged_source_revision"),
                    rs.getString("source_revision"),
                    json.readTree(rs.getString("source_snapshot")),
                    json.readTree(rs.getString("acknowledged_snapshot")),
                    rs.getLong("row_version"),
                    rs.getBoolean("merge_review"),
                    instant(rs.getObject("created_at", OffsetDateTime.class)),
                    instant(rs.getObject("updated_at", OffsetDateTime.class))))
        .list();
  }

  public List<Document> documents(Collection<UUID> ids) {
    if (ids.isEmpty()) return List.of();
    return jdbc.sql(
            "select * from account.application_preparation_documents where preparation_id in (:ids)")
        .param("ids", ids)
        .query(
            (rs, i) ->
                new Document(
                    rs.getObject("preparation_id", UUID.class),
                    rs.getString("source_document_id"),
                    rs.getString("source_fingerprint"),
                    rs.getString("state"),
                    rs.getBoolean("active")))
        .list();
  }

  public void insert(Saved s) {
    jdbc.sql(
            """
        insert into account.application_preparations(id,user_id,notice_id,acknowledged_source_revision,
          source_revision,source_snapshot,acknowledged_snapshot,created_at,updated_at)
        values(:id,:user,:notice,:source,:source,cast(:snapshot as jsonb),cast(:snapshot as jsonb),:now,:now)
        """)
        .param("id", s.id())
        .param("user", s.userId())
        .param("notice", s.noticeId())
        .param("source", s.sourceRevision())
        .param("snapshot", s.sourceSnapshot().toString())
        .param("now", s.createdAt().atOffset(ZoneOffset.UTC))
        .update();
  }

  public boolean save(Saved s, long expectedRevision) {
    return jdbc.sql(
                """
        update account.application_preparations set notice_id=:notice,status=:status,
          archived_from_status=:archived,submitted_at=:submitted,acknowledged_source_revision=:ack,
          source_revision=:source,source_snapshot=cast(:snapshot as jsonb),
          acknowledged_snapshot=cast(:ackSnapshot as jsonb),row_version=:revision,
          merge_review=:merge,updated_at=:now where id=:id and user_id=:user and row_version=:expected
        """)
            .param("id", s.id())
            .param("user", s.userId())
            .param("notice", s.noticeId())
            .param("status", s.status())
            .param("archived", s.archivedFromStatus(), java.sql.Types.VARCHAR)
            .param(
                "submitted",
                s.submittedAt() == null ? null : s.submittedAt().atOffset(ZoneOffset.UTC),
                java.sql.Types.TIMESTAMP_WITH_TIMEZONE)
            .param("ack", s.acknowledgedSourceRevision())
            .param("source", s.sourceRevision())
            .param("snapshot", s.sourceSnapshot().toString())
            .param("ackSnapshot", s.acknowledgedSnapshot().toString())
            .param("revision", s.revision())
            .param("merge", s.mergeReview())
            .param("now", s.updatedAt().atOffset(ZoneOffset.UTC))
            .param("expected", expectedRevision)
            .update()
        == 1;
  }

  public void document(Document d, Instant now) {
    jdbc.sql(
            """
        insert into account.application_preparation_documents(preparation_id,source_document_id,
          source_fingerprint,state,active,updated_at) values(:prep,:id,:fp,:state,:active,:now)
        on conflict(preparation_id,source_document_id) do update set source_fingerprint=excluded.source_fingerprint,
          state=excluded.state,active=excluded.active,updated_at=excluded.updated_at
        """)
        .param("prep", d.preparationId())
        .param("id", d.id())
        .param("fp", d.fingerprint())
        .param("state", d.state())
        .param("active", d.active())
        .param("now", now.atOffset(ZoneOffset.UTC))
        .update();
  }

  public void delete(UUID userId, UUID id) {
    jdbc.sql("delete from account.application_preparations where id=:id and user_id=:user")
        .param("id", id)
        .param("user", userId)
        .update();
  }

  public UUID resolve(UUID userId, UUID id) {
    return jdbc.sql(
            "select preparation_id from account.application_preparation_aliases where id=:id and user_id=:user")
        .param("id", id)
        .param("user", userId)
        .query(UUID.class)
        .optional()
        .orElse(id);
  }

  public void alias(UUID userId, UUID from, UUID into) {
    jdbc.sql(
            "update account.application_preparation_aliases set preparation_id=:into where user_id=:user and preparation_id=:from")
        .param("into", into)
        .param("user", userId)
        .param("from", from)
        .update();
    // 기존 alias는 삭제 전에 새 준비함을 가리키도록 옮긴다.
    delete(userId, from);
    jdbc.sql(
            "insert into account.application_preparation_aliases(id,user_id,preparation_id) values(:id,:user,:into)")
        .param("id", from)
        .param("user", userId)
        .param("into", into)
        .update();
  }

  private static Instant instant(OffsetDateTime value) {
    return value == null ? null : value.toInstant();
  }

  public record Task(
      UUID id,
      UUID preparationId,
      String title,
      LocalDate dueOn,
      boolean done,
      Instant createdAt) {}

  public List<Task> tasks(Collection<UUID> ids) {
    if (ids.isEmpty()) return List.of();
    return jdbc.sql(
            "select * from account.application_preparation_tasks where preparation_id in (:ids) order by created_at,id")
        .param("ids", ids)
        .query(
            (rs, i) ->
                new Task(
                    rs.getObject("id", UUID.class),
                    rs.getObject("preparation_id", UUID.class),
                    rs.getString("title"),
                    rs.getObject("due_on", LocalDate.class),
                    rs.getBoolean("done"),
                    instant(rs.getObject("created_at", OffsetDateTime.class))))
        .list();
  }

  public void insertTask(Task task, Instant now) {
    jdbc.sql(
            "insert into account.application_preparation_tasks(id,preparation_id,title,due_on,done,created_at,updated_at) values(:id,:prep,:title,:due,false,:now,:now)")
        .param("id", task.id())
        .param("prep", task.preparationId())
        .param("title", task.title())
        .param("due", task.dueOn(), java.sql.Types.DATE)
        .param("now", now.atOffset(ZoneOffset.UTC))
        .update();
  }

  public boolean updateTask(
      UUID preparationId, UUID id, String title, LocalDate dueOn, boolean done, Instant now) {
    return jdbc.sql(
                "update account.application_preparation_tasks set title=:title,due_on=:due,done=:done,updated_at=:now where id=:id and preparation_id=:prep")
            .param("id", id)
            .param("prep", preparationId)
            .param("title", title)
            .param("due", dueOn, java.sql.Types.DATE)
            .param("done", done)
            .param("now", now.atOffset(ZoneOffset.UTC))
            .update()
        == 1;
  }

  public boolean deleteTask(UUID preparationId, UUID id) {
    return jdbc.sql(
                "delete from account.application_preparation_tasks where id=:id and preparation_id=:prep")
            .param("id", id)
            .param("prep", preparationId)
            .update()
        == 1;
  }

  public void moveTasks(UUID from, UUID into) {
    jdbc.sql(
            "update account.application_preparation_tasks set preparation_id=:into where preparation_id=:from")
        .param("into", into)
        .param("from", from)
        .update();
  }
}
