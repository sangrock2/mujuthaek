package kr.mujuthaek.api.notice.repository;

import java.time.Instant;
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.List;
import java.util.UUID;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

/**
 * 정책 사업(창업 지원·입주 모집) 중복 후보 (notice.policy_duplicate_candidates). 같은 분야 · 같은 제목(띄어쓰기·기호 무시) · 같은
 * 지역이면 나중에 들어온 사업을 먼저 있던 사업의 후보로 올려요. 관리자가 「둘 다 둠」(KEPT_BOTH) 또는 「나중 것 숨김」(HIDDEN)을 골라요.
 */
@Repository
public class PolicyDuplicateRepository {

  /** 같은 사업으로 볼 조건 (later · earlier 별칭). 마이그레이션 V202610281300의 처음 채우기와 같은 규칙이에요. */
  private static final String SAME_POLICY =
      """
      later.field = earlier.field
      and regexp_replace(lower(later.title), '[[:space:][:punct:]·ㆍ「」『』]', '', 'g')
        = regexp_replace(lower(earlier.title), '[[:space:][:punct:]·ㆍ「」『』]', '', 'g')
      and array(select unnest(later.region_codes) order by 1)
        = array(select unnest(earlier.region_codes) order by 1)
      """;

  public static final String SAME_TITLE_REGION = "SAME_TITLE_REGION";

  private final JdbcClient jdbc;

  public PolicyDuplicateRepository(JdbcClient jdbc) {
    this.jdbc = jdbc;
  }

  /** 새로 받은 사업이 먼저 있던(숨기지 않은) 사업과 같아 보이면 후보로 올려요. 올린 수. */
  public int flag(UUID rawPolicyId, Instant now) {
    return jdbc.sql(
            "insert into notice.policy_duplicate_candidates (raw_policy_id, candidate_of, reason,"
                + " created_at) select later.raw_policy_id, earlier.raw_policy_id, :reason, :now"
                + " from notice.policy_judgments later join notice.policy_judgments earlier on "
                + SAME_POLICY
                + " and earlier.raw_policy_id <> later.raw_policy_id and earlier.hidden_at is null"
                + " where later.raw_policy_id = :id on conflict do nothing")
        .param("reason", SAME_TITLE_REGION)
        .param("now", OffsetDateTime.ofInstant(now, ZoneOffset.UTC))
        .param("id", rawPolicyId)
        .update();
  }

  /** 후보 한 쌍과 두 사업의 요약 (later가 나중에 들어온 사업). */
  public record CandidateRow(
      Side later,
      Side earlier,
      String reason,
      String status,
      Instant createdAt,
      Instant decidedAt,
      String decidedBy) {}

  /** 비교에 보여 줄 사업 요약. organization은 출처 안내의 운영 기관, 없으면 null. */
  public record Side(
      UUID rawPolicyId,
      String field,
      String title,
      String organization,
      LocalDate applyStart,
      LocalDate applyEnd,
      List<String> regionCodes,
      String detailUrl,
      Instant createdAt,
      boolean hidden) {}

  private static final String SIDE_COLUMNS =
      "%1$s.raw_policy_id, %1$s.field, %1$s.title, %1$s.info ->> 'organization',"
          + " %1$s.apply_start, %1$s.apply_end, %1$s.region_codes, %1$s.detail_url,"
          + " %1$s.created_at, %1$s.hidden_at is not null";

  /** 상태별 후보 (최근 순, 200개까지). */
  public List<CandidateRow> list(String status) {
    return jdbc.sql(
            "select "
                + SIDE_COLUMNS.formatted("l")
                + ", "
                + SIDE_COLUMNS.formatted("e")
                + ", c.reason, c.status, c.created_at, c.decided_at, c.decided_by"
                + " from notice.policy_duplicate_candidates c"
                + " join notice.policy_judgments l on l.raw_policy_id = c.raw_policy_id"
                + " join notice.policy_judgments e on e.raw_policy_id = c.candidate_of"
                + " where c.status = :status order by c.created_at desc limit 200")
        .param("status", status)
        .query(
            (rs, i) ->
                new CandidateRow(
                    side(rs, 1),
                    side(rs, 11),
                    rs.getString(21),
                    rs.getString(22),
                    rs.getObject(23, OffsetDateTime.class).toInstant(),
                    instant(rs.getObject(24, OffsetDateTime.class)),
                    rs.getString(25)))
        .list();
  }

  /** 상태별 건수 (PENDING · KEPT_BOTH · HIDDEN). */
  public java.util.Map<String, Integer> counts() {
    java.util.Map<String, Integer> out = new java.util.HashMap<>();
    jdbc.sql("select status, count(*) from notice.policy_duplicate_candidates group by status")
        .query(
            (org.springframework.jdbc.core.RowCallbackHandler)
                rs -> out.put(rs.getString(1), rs.getInt(2)));
    return out;
  }

  /** 대기 중인 후보를 결정해요. HIDDEN이면 나중에 들어온 사업을 숨겨요 (열린 목록·판정·알림에서 빠짐). 대기 중인 후보가 없으면 false. */
  public boolean decide(UUID later, UUID earlier, String status, String admin, Instant now) {
    OffsetDateTime at = OffsetDateTime.ofInstant(now, ZoneOffset.UTC);
    int updated =
        jdbc.sql(
                "update notice.policy_duplicate_candidates set status = :status, decided_at = :now,"
                    + " decided_by = :admin where raw_policy_id = :later and candidate_of = :earlier"
                    + " and status = 'PENDING'")
            .param("status", status)
            .param("now", at)
            .param("admin", admin)
            .param("later", later)
            .param("earlier", earlier)
            .update();
    if (updated == 0) {
      return false;
    }
    if ("HIDDEN".equals(status)) {
      jdbc.sql(
              "update notice.policy_judgments set hidden_at = :now, hidden_by = :admin"
                  + " where raw_policy_id = :later and hidden_at is null")
          .param("now", at)
          .param("admin", admin)
          .param("later", later)
          .update();
    }
    return true;
  }

  private static Side side(java.sql.ResultSet rs, int from) throws java.sql.SQLException {
    java.sql.Array regions = rs.getArray(from + 6);
    return new Side(
        rs.getObject(from, UUID.class),
        rs.getString(from + 1),
        rs.getString(from + 2),
        rs.getString(from + 3),
        rs.getObject(from + 4, LocalDate.class),
        rs.getObject(from + 5, LocalDate.class),
        regions == null ? List.of() : List.of((String[]) regions.getArray()),
        rs.getString(from + 7),
        rs.getObject(from + 8, OffsetDateTime.class).toInstant(),
        rs.getBoolean(from + 9));
  }

  private static Instant instant(OffsetDateTime at) {
    return at == null ? null : at.toInstant();
  }
}
