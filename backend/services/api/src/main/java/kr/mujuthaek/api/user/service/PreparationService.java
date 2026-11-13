package kr.mujuthaek.api.user.service;

import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import kr.mujuthaek.api.common.dto.response.CursorPageResponse;
import kr.mujuthaek.api.common.exception.CustomException;
import kr.mujuthaek.api.common.exception.ErrorCode;
import kr.mujuthaek.api.common.id.UuidV7;
import kr.mujuthaek.api.common.pagination.CursorKey;
import kr.mujuthaek.api.common.pagination.CursorQuery;
import kr.mujuthaek.api.notice.service.PreparationSource;
import kr.mujuthaek.api.notice.service.PreparationSourceQuery;
import kr.mujuthaek.api.user.repository.FavoriteRepository;
import kr.mujuthaek.api.user.repository.PreparationRepository;
import kr.mujuthaek.api.user.repository.PreparationRepository.Document;
import kr.mujuthaek.api.user.repository.PreparationRepository.Saved;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

/** 사용자별 준비 상태. 공고 source와 사용자 상태를 분리하고 모든 수정은 revision을 확인한다. */
@Service
public class PreparationService {
  private final PreparationRepository repository;
  private final PreparationSourceQuery sources;
  private final FavoriteService favorites;
  private final FavoriteRepository favoriteRows;
  private final Clock clock;
  private final JsonMapper json;

  public PreparationService(
      PreparationRepository repository,
      PreparationSourceQuery sources,
      FavoriteService favorites,
      FavoriteRepository favoriteRows,
      Clock clock,
      JsonMapper json) {
    this.repository = repository;
    this.sources = sources;
    this.favorites = favorites;
    this.favoriteRows = favoriteRows;
    this.clock = clock;
    this.json = json;
  }

  public record Progress(int done, int total, int checkRequired, int active, boolean partial) {}

  public record DocumentView(JsonNode source, String state, boolean active) {}

  public record TaskView(UUID id, String title, LocalDate dueOn, boolean done, Instant createdAt) {}

  public record Response(
      UUID id,
      UUID noticeId,
      String status,
      Instant submittedAt,
      long revision,
      String sourceRevision,
      String acknowledgedSourceRevision,
      boolean needsReview,
      List<String> reviewReasons,
      Progress progress,
      JsonNode nextSchedule,
      boolean favorite,
      JsonNode source,
      List<DocumentView> documents,
      List<JsonNode> removedDocuments,
      List<TaskView> tasks,
      Instant updatedAt) {}

  public record Creation(boolean created, Response preparation) {}

  @Transactional
  public Creation create(UUID userId, UUID noticeId) {
    favoriteRows.lockUser(userId);

    var all = synchronize(userId);
    var source = sources.findAll(List.of(noticeId)).get(noticeId);

    if (source == null) throw new CustomException(ErrorCode.NOTICE_NOT_FOUND);

    if (!"HOUSING".equals(source.field()))
      throw new CustomException(ErrorCode.VALIDATION_FAILED, "주거 공고만 준비함에 담을 수 있어요");

    var existing = all.stream().filter(s -> s.noticeId().equals(source.noticeId())).findFirst();

    if (existing.isPresent()) return new Creation(false, response(existing.get()));
    if (all.size() >= 200) throw new CustomException(ErrorCode.PREPARATION_LIMIT_EXCEEDED);

    favorites.add(userId, "NOTICE", source.noticeId());

    Instant now = clock.instant();

    var saved =
        new Saved(
            UuidV7.next(),
            userId,
            source.noticeId(),
            "PREPARING",
            null,
            null,
            source.revision(),
            source.revision(),
            source.content(),
            source.content(),
            0,
            false,
            now,
            now);

    repository.insert(saved);
    syncDocuments(saved, List.of());

    return new Creation(true, response(saved));
  }

  @Transactional
  public Response get(UUID userId, UUID id) {
    favoriteRows.lockUser(userId);
    return response(owned(synchronize(userId), repository.resolve(userId, id)));
  }

  @Transactional
  public CursorPageResponse<Response> list(
      UUID userId, String status, String cursor, Integer size) {
    if (status != null && !Set.of("PREPARING", "SUBMITTED", "ARCHIVED").contains(status)) invalid();

    String sort = "PREPARATIONS:" + (status == null ? "ALL" : status);
    var page = CursorQuery.of(cursor, size, sort);

    favoriteRows.lockUser(userId);

    // 최대 200건. source·서류·관심은 각각 일괄 조회한다.
    var all = synchronize(userId);
    var docs = repository.documents(all.stream().map(Saved::id).toList());
    var tasks = repository.tasks(all.stream().map(Saved::id).toList());
    var favoriteIds = favoriteNoticeIds(userId);

    var views =
        all.stream()
            .filter(s -> status == null || s.status().equals(status))
            .map(
                s ->
                    response(
                        s,
                        docs.stream().filter(d -> d.preparationId().equals(s.id())).toList(),
                        tasks.stream().filter(t -> t.preparationId().equals(s.id())).toList(),
                        favoriteIds))
            .sorted(Comparator.comparing(this::sortValue).thenComparing(r -> r.id().toString()))
            .toList();

    if (page.after() != null)
      views =
          views.stream()
              .filter(
                  r -> {
                    int compare = sortValue(r).compareTo(page.after().value());

                    return compare > 0
                        || (compare == 0
                            && r.id().toString().compareTo(page.after().id().toString()) > 0);
                  })
              .toList();

    return CursorPageResponse.from(
        views, page.size(), r -> r, r -> CursorKey.of(sort, sortValue(r), r.id()));
  }

  @Transactional
  public Response change(UUID userId, UUID id, String status, boolean restore, long revision) {
    favoriteRows.lockUser(userId);
    var s = owned(synchronize(userId), repository.resolve(userId, id));
    check(s, revision, null);

    if (restore) {
      if (status != null || !s.status().equals("ARCHIVED")) invalid();
      status = s.archivedFromStatus();
    }

    if (status == null || !Set.of("PREPARING", "SUBMITTED", "ARCHIVED").contains(status)) invalid();
    if (s.status().equals("ARCHIVED") && !restore && !status.equals("ARCHIVED")) invalid();

    String archived =
        status.equals("ARCHIVED")
            ? (s.status().equals("ARCHIVED") ? s.archivedFromStatus() : s.status())
            : null;

    Instant submitted =
        status.equals("SUBMITTED")
            ? (s.submittedAt() == null ? clock.instant() : s.submittedAt())
            : status.equals("ARCHIVED") ? s.submittedAt() : null;

    s =
        copy(
            s,
            status,
            archived,
            submitted,
            s.acknowledgedSourceRevision(),
            s.acknowledgedSnapshot(),
            s.mergeReview());

    save(s);

    return response(s);
  }

  @Transactional
  public Response document(
      UUID userId, UUID id, String documentId, String state, String sourceRevision, long revision) {
    if (!Set.of("TODO", "DONE", "NOT_APPLICABLE", "CHECK_REQUIRED").contains(state)) invalid();
    favoriteRows.lockUser(userId);

    var s = owned(synchronize(userId), repository.resolve(userId, id));
    check(s, revision, sourceRevision);
    if (s.sourceRevision().equals("unavailable")) conflict();

    var doc =
        repository.documents(List.of(s.id())).stream()
            .filter(d -> d.id().equals(documentId) && d.active())
            .findFirst()
            .orElseThrow(() -> new CustomException(ErrorCode.PREPARATION_CONFLICT));
    repository.document(
        new Document(s.id(), doc.id(), doc.fingerprint(), state, true), clock.instant());
    s =
        copy(
            s,
            s.status(),
            s.archivedFromStatus(),
            s.submittedAt(),
            s.acknowledgedSourceRevision(),
            s.acknowledgedSnapshot(),
            s.mergeReview());
    save(s);

    return response(s);
  }

  @Transactional
  public Response acknowledge(UUID userId, UUID id, String sourceRevision, long revision) {
    favoriteRows.lockUser(userId);

    var s = owned(synchronize(userId), repository.resolve(userId, id));
    check(s, revision, sourceRevision);
    if (s.sourceRevision().equals("unavailable")) conflict();
    s =
        copy(
            s,
            s.status(),
            s.archivedFromStatus(),
            s.submittedAt(),
            s.sourceRevision(),
            s.sourceSnapshot(),
            false);
    save(s);

    return response(s);
  }

  @Transactional
  public void delete(UUID userId, UUID id) {
    favoriteRows.lockUser(userId);
    repository.delete(userId, repository.resolve(userId, id));
  }

  private List<Saved> synchronize(UUID userId) {
    var all = new ArrayList<>(repository.list(userId));

    var latest = sources.findAll(all.stream().map(Saved::noticeId).toList());

    // 병합된 공고의 중복 준비함은 한 건으로 합치고, 양쪽 완료 표시는 재확인한다.
    Map<UUID, Saved> canonical = new HashMap<>();
    for (var row : all) {
      var source = latest.get(row.noticeId());

      UUID key = source == null ? row.noticeId() : source.noticeId();

      var kept = canonical.get(key);
      if (kept == null) {
        canonical.put(key, row);
        continue;
      }
      for (var d : repository.documents(List.of(row.id())))
        repository.document(
            new Document(kept.id(), d.id(), d.fingerprint(), "RECHECK_REQUIRED", d.active()),
            clock.instant());
      repository.moveTasks(row.id(), kept.id());
      repository.alias(userId, row.id(), kept.id());

      Instant submitted = kept.submittedAt() != null ? kept.submittedAt() : row.submittedAt();

      var merged =
          copy(
              kept,
              "PREPARING",
              null,
              submitted,
              kept.acknowledgedSourceRevision(),
              kept.acknowledgedSnapshot(),
              true);
      save(merged);
      syncDocuments(merged, repository.documents(List.of(merged.id())));
      canonical.put(key, merged);
    }
    var docs = repository.documents(canonical.values().stream().map(Saved::id).toList());

    List<Saved> result = new ArrayList<>();
    for (var s : canonical.values()) {
      var source = latest.get(s.noticeId());

      boolean available = source != null && source.field().equals("HOUSING");

      String revision = available ? source.revision() : "unavailable";

      boolean retarget = available && !source.noticeId().equals(s.noticeId());
      if (!revision.equals(s.sourceRevision()) || retarget) {
        JsonNode snapshot = available ? source.content() : json.createObjectNode();

        var next =
            new Saved(
                s.id(),
                s.userId(),
                available ? source.noticeId() : s.noticeId(),
                s.status(),
                s.archivedFromStatus(),
                s.submittedAt(),
                s.acknowledgedSourceRevision(),
                revision,
                snapshot,
                available ? s.acknowledgedSnapshot() : json.createObjectNode(),
                s.revision() + 1,
                s.mergeReview() || retarget,
                s.createdAt(),
                clock.instant());
        save(next);
        s = next;
        syncDocuments(s, docs.stream().filter(d -> d.preparationId().equals(next.id())).toList());
      }
      result.add(s);
    }
    return result;
  }

  private void syncDocuments(Saved s, List<Document> existing) {
    Map<String, Document> old = new HashMap<>();
    existing.forEach(d -> old.put(d.id(), d));

    Set<String> ids = new HashSet<>();

    boolean incomplete = false;
    for (var doc : s.sourceSnapshot().path("requiredDocuments")) {
      String id = doc.path("id").asString("");
      if (id.isBlank() || !ids.add(id)) incomplete = true;
    }
    if (incomplete) ids.clear();
    for (var d : existing)
      if (!ids.contains(d.id()))
        repository.document(
            new Document(s.id(), d.id(), d.fingerprint(), d.state(), false), clock.instant());
    if (incomplete) return;
    for (var doc : s.sourceSnapshot().path("requiredDocuments")) {
      String id = doc.path("id").asString();

      String fp = PreparationSource.fingerprint(doc);

      var previous = old.get(id);

      String state =
          previous == null
              ? initialState(doc)
              : !previous.active() || !previous.fingerprint().equals(fp)
                  ? "RECHECK_REQUIRED"
                  : previous.state();
      repository.document(new Document(s.id(), id, fp, state, true), clock.instant());
    }
  }

  static String initialState(JsonNode doc) {
    String appliesTo = doc.path("appliesTo").asString("").strip();

    return doc.path("group").asString("").equals("COMMON")
            && doc.path("targetGroups").isEmpty()
            && Set.of("", "신청자", "전체 신청자", "모든 신청자", "신청자 전원").contains(appliesTo)
        ? "TODO"
        : "CHECK_REQUIRED";
  }

  private Response response(Saved s) {
    Set<UUID> ids = favoriteNoticeIds(s.userId());

    return response(
        s, repository.documents(List.of(s.id())), repository.tasks(List.of(s.id())), ids);
  }

  private Set<UUID> favoriteNoticeIds(UUID userId) {
    var ids =
        favoriteRows.page(userId, "NOTICE", null, null, 200).stream()
            .map(FavoriteRepository.Favorite::targetId)
            .toList();

    Set<UUID> result = new HashSet<>(ids);
    sources.findAll(ids).values().forEach(source -> result.add(source.noticeId()));

    return result;
  }

  private Response response(
      Saved s, List<Document> docs, List<PreparationRepository.Task> tasks, Set<UUID> favorites) {
    List<String> reasons = new ArrayList<>();

    var content = s.sourceSnapshot();

    boolean available = !s.sourceRevision().equals("unavailable");
    if (!available) reasons.add("SOURCE_UNAVAILABLE");
    else if (!s.sourceRevision().equals(s.acknowledgedSourceRevision())) {
      for (String section :
          List.of(
              "header",
              "requiredDocuments",
              "schedules",
              "followUps",
              "unitTypes",
              "conditions",
              "heldItems",
              "files",
              "guidance",
              "selectionRules"))
        if (!PreparationSource.fingerprint(content.path(section))
            .equals(PreparationSource.fingerprint(s.acknowledgedSnapshot().path(section))))
          reasons.add(section);
      if (reasons.isEmpty()) reasons.add("VERSION_CHANGED");
    }
    if (s.mergeReview()) reasons.add("NOTICE_MERGED");

    Map<String, Document> byId = new HashMap<>();
    docs.forEach(d -> byId.put(d.id(), d));

    List<DocumentView> views = new ArrayList<>();

    Set<String> seen = new HashSet<>();

    boolean incomplete = false;
    for (var doc : content.path("requiredDocuments")) {
      String id = doc.path("id").asString("");
      if (id.isBlank() || !seen.add(id)) {
        incomplete = true;
        continue;
      }
      var state = byId.get(id);
      if (state != null && state.active()) views.add(new DocumentView(doc, state.state(), true));
    }
    if (incomplete) reasons.add("SOURCE_INCOMPLETE");

    int done = 0, total = 0, check = 0;
    for (var doc : views) {
      if (!doc.state().equals("NOT_APPLICABLE")) total++;
      if (doc.state().equals("DONE")) done++;
      if (doc.state().equals("CHECK_REQUIRED") || doc.state().equals("RECHECK_REQUIRED")) check++;
    }
    if (views.stream().anyMatch(d -> d.state().equals("RECHECK_REQUIRED")))
      reasons.add("DOCUMENT_RECHECK");

    boolean partial =
        content
            .path("heldItems")
            .valueStream()
            .anyMatch(
                n ->
                    n.path("section")
                        .asString("")
                        .toLowerCase(java.util.Locale.ROOT)
                        .contains("document"));

    List<JsonNode> removed = new ArrayList<>();
    if (available)
      for (var d : s.acknowledgedSnapshot().path("requiredDocuments"))
        if (!seen.contains(d.path("id").asString())) removed.add(d);

    return new Response(
        s.id(),
        s.noticeId(),
        s.status(),
        s.submittedAt(),
        s.revision(),
        s.sourceRevision(),
        s.acknowledgedSourceRevision(),
        !reasons.isEmpty(),
        List.copyOf(reasons),
        new Progress(done, total, check, views.size(), partial),
        nextSchedule(content),
        favorites.contains(s.noticeId()),
        content,
        views,
        removed,
        tasks.stream()
            .map(t -> new TaskView(t.id(), t.title(), t.dueOn(), t.done(), t.createdAt()))
            .toList(),
        s.updatedAt());
  }

  private JsonNode nextSchedule(JsonNode content) {
    List<JsonNode> schedules = new ArrayList<>();
    content.path("schedules").forEach(schedules::add);
    content.path("followUps").forEach(f -> f.path("schedules").forEach(schedules::add));

    String today = LocalDate.now(clock).toString();

    return schedules.stream()
        .filter(
            s -> {
              String end = s.path("endsAt").asString("");
              if (end.length() == 10) return end.compareTo(today) >= 0;
              try {
                return !java.time.OffsetDateTime.parse(end).toInstant().isBefore(clock.instant());
              } catch (java.time.format.DateTimeParseException e) {
                return false;
              }
            })
        .min(Comparator.comparing(s -> s.path("endsAt").asString()))
        .orElse(null);
  }

  private String sortValue(Response r) {
    String end = r.source().path("header").path("applyEnd").asString("");
    if (end.isEmpty() || end.compareTo(LocalDate.now(clock).toString()) < 0) end = "9999-99-99";

    return (r.needsReview() ? "0" : "1") + ":" + end + ":" + r.id();
  }

  private Saved copy(
      Saved s,
      String status,
      String archived,
      Instant submitted,
      String ack,
      JsonNode ackSnapshot,
      boolean merge) {
    return new Saved(
        s.id(),
        s.userId(),
        s.noticeId(),
        status,
        archived,
        submitted,
        ack,
        s.sourceRevision(),
        s.sourceSnapshot(),
        ackSnapshot,
        s.revision() + 1,
        merge,
        s.createdAt(),
        clock.instant());
  }

  private void save(Saved s) {
    if (!repository.save(s, s.revision() - 1)) conflict();
  }

  private Saved owned(List<Saved> all, UUID id) {
    return all.stream()
        .filter(s -> s.id().equals(id))
        .findFirst()
        .orElseThrow(() -> new CustomException(ErrorCode.PREPARATION_NOT_FOUND));
  }

  private void check(Saved s, long revision, String source) {
    if (s.revision() != revision || (source != null && !source.equals(s.sourceRevision())))
      conflict();
  }

  private static void conflict() {
    throw new CustomException(ErrorCode.PREPARATION_CONFLICT);
  }

  private static void invalid() {
    throw new CustomException(ErrorCode.VALIDATION_FAILED);
  }

  @Transactional
  public Response addTask(UUID userId, UUID id, String title, LocalDate dueOn, long revision) {
    String checked = taskTitle(title);
    favoriteRows.lockUser(userId);

    var s = owned(synchronize(userId), repository.resolve(userId, id));
    check(s, revision, null);
    if (repository.tasks(List.of(s.id())).size() >= 30)
      throw new CustomException(ErrorCode.PREPARATION_TASK_LIMIT_EXCEEDED);
    repository.insertTask(
        new PreparationRepository.Task(
            UuidV7.next(), s.id(), checked, dueOn, false, clock.instant()),
        clock.instant());

    return taskChanged(s);
  }

  @Transactional
  public Response updateTask(
      UUID userId,
      UUID id,
      UUID taskId,
      String title,
      LocalDate dueOn,
      boolean done,
      long revision) {
    String checked = taskTitle(title);
    favoriteRows.lockUser(userId);

    var s = owned(synchronize(userId), repository.resolve(userId, id));
    check(s, revision, null);
    if (!repository.updateTask(s.id(), taskId, checked, dueOn, done, clock.instant()))
      throw new CustomException(ErrorCode.PREPARATION_TASK_NOT_FOUND);

    return taskChanged(s);
  }

  @Transactional
  public Response deleteTask(UUID userId, UUID id, UUID taskId, long revision) {
    if (revision < 0) invalid();
    favoriteRows.lockUser(userId);

    var s = owned(synchronize(userId), repository.resolve(userId, id));
    check(s, revision, null);
    if (!repository.deleteTask(s.id(), taskId))
      throw new CustomException(ErrorCode.PREPARATION_TASK_NOT_FOUND);

    return taskChanged(s);
  }

  private Response taskChanged(Saved s) {
    var changed =
        copy(
            s,
            s.status(),
            s.archivedFromStatus(),
            s.submittedAt(),
            s.acknowledgedSourceRevision(),
            s.acknowledgedSnapshot(),
            s.mergeReview());
    save(changed);

    return response(changed);
  }

  private String taskTitle(String title) {
    if (title == null || title.strip().isEmpty() || title.length() > 120) invalid();

    return title.strip().replaceAll("\\s+", " ");
  }
}
