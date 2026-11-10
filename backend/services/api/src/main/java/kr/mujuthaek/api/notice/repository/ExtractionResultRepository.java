package kr.mujuthaek.api.notice.repository;

import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;
import java.util.UUID;
import kr.mujuthaek.api.notice.domain.IngestionOutcome;
import kr.mujuthaek.api.notice.domain.ReviewStatus;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

/** 받은 추출 결과 기록 (notice.extraction_results). 공개하지 않은 결과도 여기 남아요. */
@Repository
public class ExtractionResultRepository {

  /** 원래 공고가 아직 공개되지 않아 기다리는 정정 공고의 이유 코드. */
  public static final String PARENT_NOT_PUBLISHED = "PARENT_NOT_PUBLISHED";

  /** 정정·후속 안내인데 원래 공고 연결(supersedesPostId)이 없어 보류함. 연결된 원본 버전이 오면 그때 반영해요. */
  public static final String UNLINKED_RELATED_NOTICE = "UNLINKED_RELATED_NOTICE";

  /** 기다리던 결과의 저장본이 지금 계약에 맞지 않아 반영하지 못함 (원래 공고는 공개돼요). */
  public static final String STORED_PAYLOAD_INVALID = "STORED_PAYLOAD_INVALID";

  private final JdbcClient jdbc;

  public ExtractionResultRepository(JdbcClient jdbc) {
    this.jdbc = jdbc;
  }

  /**
   * 이미 받은 이벤트인지. 수신 기록은 반영과 같은 트랜잭션에 남아서, 반영이 실패해 되돌려지면 기록도 없어 다시 받으면 처음부터 처리돼요. 공통 수신
   * 도우미(EventInbox)는 처리가 끝난 뒤 따로 기록하므로, 그 사이에 멈춰 같은 이벤트가 다시 와도 여기서 걸러요.
   */
  /**
   * 같은 eventId를 처리하는 트랜잭션끼리 줄을 세워요(트랜잭션이 끝나면 풀려요). 같은 이벤트가 동시에 오면(재전송·중복 발행·소비자 여럿) 「처리했나 → 처리」 사이에
   * 끼어들어 처리 기록의 기본 키에서 부딪혀 예외(→ 재시도·실패 큐)가 나던 것을, 뒤에 온 것이 앞의 커밋을 기다렸다가 DUPLICATE로 끝나게 해요
   * (2026-11-01 동시성 시험: 100개 동시에 9개 예외).
   */
  public void lock(UUID eventId) {
    jdbc.sql(
            "select pg_advisory_xact_lock(hashtextextended('extraction-event:' || cast(:id as text), 0))")
        .param("id", eventId)
        .query((rs, i) -> 1)
        .list();
  }

  public boolean exists(UUID eventId) {
    return jdbc.sql("select exists (select 1 from notice.extraction_results where event_id = :id)")
        .param("id", eventId)
        .query(Boolean.class)
        .single();
  }

  public void insert(
      UUID eventId,
      UUID rawPostId,
      int rawVersion,
      ReviewStatus reviewStatus,
      IngestionOutcome outcome,
      String reason,
      UUID noticeId,
      UUID supersedesPostId,
      String payloadJson,
      Instant receivedAt) {
    jdbc.sql(
            "insert into notice.extraction_results (event_id, raw_post_id, raw_version,"
                + " review_status, outcome, reason, notice_id, supersedes_post_id, payload,"
                + " received_at) values (:eventId, :rawPostId, :rawVersion, :reviewStatus,"
                + " :outcome, :reason, :noticeId, :supersedes, cast(:payload as jsonb),"
                + " :receivedAt)")
        .param("eventId", eventId)
        .param("rawPostId", rawPostId)
        .param("rawVersion", rawVersion)
        .param("reviewStatus", reviewStatus.name())
        .param("outcome", outcome.name())
        .param("reason", reason)
        .param("noticeId", noticeId)
        .param("supersedes", supersedesPostId)
        .param("payload", payloadJson)
        .param("receivedAt", receivedAt.atOffset(ZoneOffset.UTC))
        .update();
  }

  /** 기다리던 결과를 나중에 반영했을 때 결과를 바꿔요. */
  public void updateOutcome(UUID eventId, IngestionOutcome outcome, String reason, UUID noticeId) {
    jdbc.sql(
            "update notice.extraction_results set outcome = :outcome, reason = :reason,"
                + " notice_id = :noticeId where event_id = :eventId")
        .param("eventId", eventId)
        .param("outcome", outcome.name())
        .param("reason", reason)
        .param("noticeId", noticeId)
        .update();
  }

  /** 이 원본 글이 공개되기를 기다리는 정정 공고. 받은 순서대로. */
  public List<WaitingResult> findWaitingFor(UUID parentRawPostId) {
    return jdbc.sql(
            "select event_id, payload::text as payload from notice.extraction_results"
                + " where supersedes_post_id = :parent and outcome = 'HELD'"
                + " and reason = :reason order by received_at, event_id")
        .param("parent", parentRawPostId)
        .param("reason", PARENT_NOT_PUBLISHED)
        .query(
            (rs, i) ->
                new WaitingResult(rs.getObject("event_id", UUID.class), rs.getString("payload")))
        .list();
  }

  public record WaitingResult(UUID eventId, String payloadJson) {}
}
