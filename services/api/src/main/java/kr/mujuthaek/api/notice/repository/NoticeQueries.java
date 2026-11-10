package kr.mujuthaek.api.notice.repository;

import java.sql.Date;
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import kr.mujuthaek.api.common.pagination.CursorKey;
import kr.mujuthaek.api.notice.dto.request.NoticeListFilter;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Repository;

/**
 * 공개된(현재 버전이 있고 숨기지 않은) 공고 조회. 다른 공고에 합쳐진 공고는 목록에서 빠지고, 그 ID로 상세·이력을 물으면 합친 공고가 나와요(관심 공고·알림 링크가
 * 끊기지 않게).
 */
@Repository
public class NoticeQueries {

  /** 마감일 없는 공고는 마감 임박순 맨 뒤, 공고일 없는 공고는 최신순 맨 뒤. */
  static final LocalDate NO_END = LocalDate.of(9999, 12, 31);

  static final LocalDate NO_POSTED = LocalDate.of(1, 1, 1);

  private final NamedParameterJdbcTemplate jdbc;

  public NoticeQueries(JdbcTemplate jdbc) {
    this.jdbc = new NamedParameterJdbcTemplate(jdbc);
  }

  public record ListRow(
      UUID id,
      String field,
      String title,
      String provider,
      String noticeType,
      String regionCode,
      LocalDate applyStart,
      LocalDate applyEnd,
      LocalDate postedOn,
      String status,
      boolean needsCheck) {}

  public List<ListRow> list(NoticeListFilter f, CursorKey after, int fetchSize) {
    var params =
        new MapSqlParameterSource()
            .addValue("field", f.field())
            .addValue("statuses", f.statuses())
            .addValue("limit", fetchSize);
    StringBuilder sql =
        new StringBuilder(
            """
            select id, field, title, provider, notice_type, region_code, apply_start, apply_end, posted_on,
                   status, needs_check
            from notice.notices n
            where current_version > 0 and not hidden and merged_into is null and field = :field
              and status in (:statuses)
            """);
    if (!f.regionCodes().isEmpty()) {
      // 공고가 걸친 모든 지역(notice_regions)으로 찾아요. 시도(2자리·xx000)면 그 시도의 모든 지역, 시군구면 그 시군구와 그 시군구를 품는
      // 대상 지역 전체(whole: 「대구 전체」 → 대구 중구, 「고양시 전체」 → 덕양구). 전국 대상 공고는 어느 지역으로도 나와요
      sql.append(
          " and (nationwide or exists (select 1 from notice.notice_regions r where r.notice_id = n.id"
              + " and (false");
      if (!f.sidoCodes().isEmpty()) {
        sql.append(" or left(r.sigungu_code, 2) in (:sido)");
        params.addValue("sido", f.sidoCodes());
      }
      if (!f.sigunguCodes().isEmpty()) {
        sql.append(
            " or r.sigungu_code in (:sigungu)"
                + " or (r.whole and r.sigungu_code in (:sigunguSido, :sigunguCity))");
        params.addValue("sigungu", f.sigunguCodes());
        params.addValue(
            "sigunguSido", f.sigunguCodes().stream().map(c -> c.substring(0, 2) + "000").toList());
        params.addValue(
            "sigunguCity", f.sigunguCodes().stream().map(c -> c.substring(0, 4) + "0").toList());
      }
      sql.append(")))");
    }
    if ("BUY".equals(f.tenure())) {
      sql.append(" and notice_type in (:buy)");
      params.addValue("buy", NoticeListFilter.BUY_TYPES);
    } else if ("RENT".equals(f.tenure())) {
      // 유형을 못 정한 공고(null)도 빌려서: 분양이 아니면 임대예요
      sql.append(" and (notice_type is null or notice_type not in (:buy))");
      params.addValue("buy", NoticeListFilter.BUY_TYPES);
    }
    if (!f.noticeTypes().isEmpty()) {
      sql.append(" and notice_type in (:types)");
      params.addValue("types", f.noticeTypes());
    }
    if (f.applyEndFrom() != null) {
      sql.append(" and apply_end >= :applyEndFrom");
      params.addValue("applyEndFrom", Date.valueOf(f.applyEndFrom()));
    }
    if (f.applyEndTo() != null) {
      sql.append(" and apply_end <= :applyEndTo");
      params.addValue("applyEndTo", Date.valueOf(f.applyEndTo()));
    }
    if (!f.providers().isEmpty()) {
      sql.append(" and provider in (:providers)");
      params.addValue("providers", f.providers());
    }
    // 검색어: 낱말마다 제목에 들어 있어야 해요 (공백을 빼고 소문자로 비교, Keywords)
    List<String> patterns = f.keywords().likePatterns();
    for (int i = 0; i < patterns.size(); i++) {
      sql.append(" and lower(regexp_replace(title, '\\s+', '', 'g')) like :kw")
          .append(i)
          .append(" escape '\\'");
      params.addValue("kw" + i, patterns.get(i));
    }
    if ("LATEST".equals(f.sort())) {
      String key = "coalesce(posted_on, date '" + NO_POSTED + "')";
      if (after != null) {
        sql.append(" and (").append(key).append(", id) < (cast(:afterValue as date), :afterId)");
      }
      sql.append(" order by ").append(key).append(" desc, id desc");
    } else {
      String key = "coalesce(apply_end, date '" + NO_END + "')";
      if (after != null) {
        sql.append(" and (").append(key).append(", id) > (cast(:afterValue as date), :afterId)");
      }
      sql.append(" order by ").append(key).append(" asc, id asc");
    }
    if (after != null) {
      params.addValue("afterValue", after.value()).addValue("afterId", after.id());
    }
    sql.append(" limit :limit");
    return jdbc.query(
        sql.toString(),
        params,
        (rs, i) ->
            new ListRow(
                rs.getObject(1, UUID.class),
                rs.getString(2),
                rs.getString(3),
                rs.getString(4),
                rs.getString(5),
                rs.getString(6),
                rs.getObject(7, LocalDate.class),
                rs.getObject(8, LocalDate.class),
                rs.getObject(9, LocalDate.class),
                rs.getString(10),
                rs.getBoolean(11)));
  }

  /** 공개된 공고의 현재 버전 (목록 값 + 저장한 payload). 숨김·공개 전·없는 공고는 빈 값. */
  public record CurrentRow(
      ListRow row,
      String supplyTypeText,
      String detailUrl,
      int version,
      boolean reviewed,
      OffsetDateTime updatedAt,
      String payload) {}

  public Optional<CurrentRow> current(UUID noticeId) {
    return jdbc
        .query(
            """
            select n.id, n.field, n.title, n.provider, n.notice_type, n.region_code, n.apply_start,
                   n.apply_end, n.posted_on, n.supply_type_text, n.detail_url, n.current_version,
                   n.reviewed, n.updated_at, v.payload::text, n.status, n.needs_check
            from notice.notices n
            join notice.notice_versions v on v.notice_id = n.id and v.version = n.current_version
            where n.id = coalesce((select m.merged_into from notice.notices m where m.id = :id), :id)
              and n.current_version > 0 and not n.hidden
            """,
            new MapSqlParameterSource("id", noticeId),
            (rs, i) ->
                new CurrentRow(
                    new ListRow(
                        rs.getObject(1, UUID.class),
                        rs.getString(2),
                        rs.getString(3),
                        rs.getString(4),
                        rs.getString(5),
                        rs.getString(6),
                        rs.getObject(7, LocalDate.class),
                        rs.getObject(8, LocalDate.class),
                        rs.getObject(9, LocalDate.class),
                        rs.getString(16),
                        rs.getBoolean(17)),
                    rs.getString(10),
                    rs.getString(11),
                    rs.getInt(12),
                    rs.getBoolean(13),
                    rs.getObject(14, OffsetDateTime.class),
                    rs.getString(15)))
        .stream()
        .findFirst();
  }

  /**
   * 판정용 공고 한 줄. regionCodes는 지역 색인(시군구 5자리), frameJson은 현재 버전의 판정 틀(없으면 null), detailUrl은 기관 원문
   * 주소(없으면 null).
   */
  public record JudgmentRow(
      UUID id,
      int version,
      String title,
      LocalDate applyStart,
      LocalDate applyEnd,
      boolean nationwide,
      List<String> regionCodes,
      String frameJson,
      String detailUrl) {}

  /**
   * 판정용 정책 한 줄 (notice.policy_judgments). regionCodes는 시군구 5자리, 빈 목록은 전국. detailUrl은 수집한 정책 원문
   * 주소(없으면 null).
   */
  public record PolicyRow(
      UUID rawPolicyId,
      int version,
      String title,
      LocalDate applyStart,
      LocalDate applyEnd,
      List<String> regionCodes,
      String frameJson,
      String detailUrl) {}

  /**
   * 이 분야(STARTUP_SUPPORT·SPACE_RECRUITMENT)의 열린 정책 판정 틀 전부 (마감일 순). 마감일이 오늘보다 앞이면 빼요. 마감일이 없으면 상시
   * 모집(apply_always)일 때만 넣고, 상시가 아닌데 마감일을 모르면 빼요 (공고가 UNKNOWN을 빼는 것과 같은 규칙, 리뷰 2026-10-23: 마감된 사업이
   * 열려 보였음). 마감일 대신 「예산 소진 시까지」(info.applyNote)라고 적힌 사업은 지금 열려 있어 넣어요. 검수 대기(IN_REVIEW) 틀은 공개하지 않아요
   * (이전 규칙으로 저장된 줄 포함).
   */
  /** 정책 출처 안내 JSON (policy_judgments.info). 없으면 그 정책은 빠져요. */
  public java.util.Map<UUID, String> policyInfos(java.util.Collection<UUID> rawPolicyIds) {
    if (rawPolicyIds.isEmpty()) {
      return java.util.Map.of();
    }
    java.util.Map<UUID, String> out = new java.util.HashMap<>();
    jdbc.query(
        "select raw_policy_id, info::text from notice.policy_judgments"
            + " where raw_policy_id in (:ids) and info is not null",
        new MapSqlParameterSource("ids", rawPolicyIds),
        rs -> {
          out.put(rs.getObject(1, UUID.class), rs.getString(2));
        });
    return out;
  }

  public List<PolicyRow> openPolicies(String field, LocalDate today) {
    return jdbc.query(
        """
        select raw_policy_id, raw_version, title, apply_start, apply_end, region_codes, frame::text,
               detail_url
        from notice.policy_judgments
        where field = :field and review_status <> 'IN_REVIEW' and hidden_at is null
          and (apply_end >= :today
               or (apply_end is null and (apply_always or info->>'applyNote' is not null)))
        order by apply_end nulls last, raw_policy_id
        """,
        new MapSqlParameterSource("field", field).addValue("today", today),
        (rs, i) ->
            new PolicyRow(
                rs.getObject(1, UUID.class),
                rs.getInt(2),
                rs.getString(3),
                rs.getObject(4, LocalDate.class),
                rs.getObject(5, LocalDate.class),
                List.of((String[]) rs.getArray(6).getArray()),
                rs.getString(7),
                rs.getString(8)));
  }

  /**
   * 정책 요약 한 줄 (알림·관심 정책). organization은 출처 안내의 기관 이름(없으면 null). applyNote는 마감일 대신 적힌 신청 기간 안내(「예산
   * 소진 시까지」, 없으면 null).
   */
  public record PolicySummaryRow(
      UUID rawPolicyId,
      int version,
      String field,
      String title,
      String organization,
      LocalDate applyStart,
      LocalDate applyEnd,
      boolean applyAlways,
      List<String> regionCodes,
      String detailUrl,
      String applyNote) {}

  /** 이 공고에 합쳐진 공고 ID들 (합치기는 한 단계로 펴서 저장해요: 합쳐진 공고에 다시 합친 공고도 남은 공고를 가리킴). */
  public List<UUID> mergedFrom(UUID noticeId) {
    return jdbc.query(
        "select id from notice.notices where merged_into = :id order by id",
        new MapSqlParameterSource("id", noticeId),
        (rs, i) -> rs.getObject(1, UUID.class));
  }

  private static final String POLICY_SUMMARY_COLUMNS =
      """
      select raw_policy_id, raw_version, field, title, info ->> 'organization', apply_start,
             apply_end, apply_always, region_codes, detail_url, info ->> 'applyNote'
      from notice.policy_judgments
      """;

  /** 공개된 정책 하나 (검수 대기 틀은 빼요). 마감된 정책도 줘요. */
  public java.util.Optional<PolicySummaryRow> policySummary(UUID rawPolicyId) {
    return jdbc
        .query(
            POLICY_SUMMARY_COLUMNS
                + " where raw_policy_id = :id and review_status <> 'IN_REVIEW' and hidden_at is null",
            new MapSqlParameterSource("id", rawPolicyId),
            (rs, i) -> policySummaryRow(rs))
        .stream()
        .findFirst();
  }

  /** 공개된 정책 여러 개를 한 번에 (관심 목록용, 검수 대기 틀·숨김은 빼요). 마감된 정책도 줘요. */
  public List<PolicySummaryRow> policySummaries(java.util.Collection<UUID> rawPolicyIds) {
    if (rawPolicyIds.isEmpty()) {
      return List.of();
    }
    return jdbc.query(
        POLICY_SUMMARY_COLUMNS
            + " where raw_policy_id in (:ids) and review_status <> 'IN_REVIEW' and hidden_at is null",
        new MapSqlParameterSource("ids", rawPolicyIds),
        (rs, i) -> policySummaryRow(rs));
  }

  /**
   * 마감일이 dates 중 하나이고 오늘 신청할 수 있는 정책 (검수 대기·아직 시작 전·중복으로 숨긴 정책은 빼요). 마감일 순. 숨긴 정책을 빼지 않아 관리자가 숨긴 중복
   * 정책에도 D-3·D-1 알림이 갔어요(2026-11-10 코드 검토, 다른 정책 조회는 #157에서 뺐음).
   */
  public List<PolicySummaryRow> openPoliciesClosingOn(
      java.util.Collection<LocalDate> dates, LocalDate today) {
    if (dates.isEmpty()) {
      return List.of();
    }
    return jdbc.query(
        POLICY_SUMMARY_COLUMNS
            + """
             where review_status <> 'IN_REVIEW' and hidden_at is null and apply_end in (:dates)
               and (apply_start is null or apply_start <= :today)
             order by apply_end, raw_policy_id
            """,
        new MapSqlParameterSource("dates", List.copyOf(dates)).addValue("today", today),
        (rs, i) -> policySummaryRow(rs));
  }

  private static PolicySummaryRow policySummaryRow(java.sql.ResultSet rs)
      throws java.sql.SQLException {
    return new PolicySummaryRow(
        rs.getObject(1, UUID.class),
        rs.getInt(2),
        rs.getString(3),
        rs.getString(4),
        rs.getString(5),
        rs.getObject(6, LocalDate.class),
        rs.getObject(7, LocalDate.class),
        rs.getBoolean(8),
        List.of((String[]) rs.getArray(9).getArray()),
        rs.getString(10),
        rs.getString(11));
  }

  /** 판정용 공고 한 줄 (맞춤 목록). payload는 현재 버전의 판정 틀·원문(notice) 부분만. */
  public record JudgingRow(UUID id, int version, String field, String noticeType, String payload) {}

  /** 공개된 공고의 현재 버전 번호 (판정 틀 기억을 맞춰 보려고). 숨김·공개 전·합쳐진 공고는 빠져요. */
  public java.util.Map<UUID, Integer> currentVersions(java.util.Collection<UUID> ids) {
    java.util.Map<UUID, Integer> out = new java.util.HashMap<>();
    jdbc.query(
        """
        select id, current_version from notice.notices
        where id in (:ids) and current_version > 0 and not hidden
        """,
        new MapSqlParameterSource("ids", ids),
        rs -> {
          out.put(rs.getObject(1, UUID.class), rs.getInt(2));
        });
    return out;
  }

  /** 열린 공고 ID (모집 예정·중·상시·모름, 마감 임박순). 판정 캐시 미리 채우기용. */
  public List<UUID> openNoticeIds(int limit) {
    return jdbc.query(
        """
        select id from notice.notices
        where current_version > 0 and not hidden and merged_into is null
          and status in ('UPCOMING', 'APPLYING', 'ALWAYS', 'UNKNOWN')
        order by coalesce(apply_end, date '9999-12-31'), id
        limit :limit
        """,
        new MapSqlParameterSource("limit", limit),
        (rs, i) -> rs.getObject(1, UUID.class));
  }

  /**
   * 공고 여러 개의 판정용 내용을 한 번에. 숨김·공개 전 공고는 빠져요.
   *
   * <p>payload의 notice는 판정 틀(공급 유형 가격·보류 항목·추출 범위)을 만드는 데 쓰는 칸만 남겨요. 상세 화면용 큰 칸(근거·자격 원문·서류·선정
   * 기준·안내·일정)은 빼서 DB가 보내고 앱이 읽는 양을 줄여요(공고 하나에 notice가 14만 자, 근거·자격만 2만 자 넘게). 남긴 칸만으로 만든 판정 틀이 원문
   * 전체로 만든 것과 같은지는 NoticeSearchLoadTest가 봐요.
   */
  public List<JudgingRow> judgingRows(java.util.Collection<UUID> ids) {
    return jdbc.query(
        """
        select n.id, n.current_version, n.field, n.notice_type,
               jsonb_build_object('judgment', v.payload -> 'judgment',
                                  'notice', (v.payload -> 'notice') - array[
                                      'evidence', 'eligibility', 'requiredDocuments', 'selectionRules',
                                      'guidance', 'schedules', 'documents', 'sourceReferences', 'input'])::text
        from notice.notices n
        join notice.notice_versions v on v.notice_id = n.id and v.version = n.current_version
        where n.id in (:ids) and n.current_version > 0 and not n.hidden
        """,
        new MapSqlParameterSource("ids", ids),
        (rs, i) ->
            new JudgingRow(
                rs.getObject(1, UUID.class),
                rs.getInt(2),
                rs.getString(3),
                rs.getString(4),
                rs.getString(5)));
  }

  /** 이 분야의 열린 공개 공고 전부: 접수예정·접수중·상시 (합쳐진·숨긴 공고 제외, 마감일 순). 상태를 단정할 수 없는 UNKNOWN은 빼요. */
  public List<JudgmentRow> openForJudgment(String field) {
    return jdbc.query(
        """
        select n.id, n.current_version, n.title, n.apply_start, n.apply_end, n.nationwide,
               array(select r.sigungu_code from notice.notice_regions r
                     where r.notice_id = n.id order by r.sigungu_code) as regions,
               case when jsonb_typeof(v.payload -> 'judgment') = 'object'
                    then (v.payload -> 'judgment')::text end as frame,
               n.detail_url
        from notice.notices n
        join notice.notice_versions v on v.notice_id = n.id and v.version = n.current_version
        where n.field = :field and n.current_version > 0 and not n.hidden
          and n.merged_into is null and n.status in ('UPCOMING', 'APPLYING', 'ALWAYS')
        order by n.apply_end nulls last, n.id
        """,
        new MapSqlParameterSource("field", field),
        (rs, i) ->
            new JudgmentRow(
                rs.getObject(1, UUID.class),
                rs.getInt(2),
                rs.getString(3),
                rs.getObject(4, LocalDate.class),
                rs.getObject(5, LocalDate.class),
                rs.getBoolean(6),
                List.of((String[]) rs.getArray(7).getArray()),
                rs.getString(8),
                rs.getString(9)));
  }

  /** 요약 한 줄. requestedId는 물은 ID, id는 합친 공고면 합친(남은) 공고 ID. regionCodes는 지역 색인(시군구 5자리). */
  public record SummaryRow(
      UUID requestedId,
      UUID id,
      int version,
      String field,
      String title,
      String provider,
      String noticeType,
      String status,
      LocalDate applyStart,
      LocalDate applyEnd,
      boolean nationwide,
      List<String> regionCodes,
      String detailUrl) {}

  /**
   * 여러 공고의 요약을 한 번에 (상세와 같이 합쳐진 공고 ID는 합친 공고로 바꿔요). 숨김·공개 전·없는 공고는 빠져요. 합침은 늘 마지막 공고를 가리키게 저장해서
   * (NoticeRepository.mergeInto) 한 번만 따라가면 돼요.
   */
  public List<SummaryRow> summaries(java.util.Collection<UUID> ids) {
    if (ids.isEmpty()) {
      return List.of();
    }
    return jdbc.query(
        """
        select m.id, n.id, n.current_version, n.field, n.title, n.provider, n.notice_type, n.status,
               n.apply_start, n.apply_end, n.nationwide,
               array(select r.sigungu_code from notice.notice_regions r
                     where r.notice_id = n.id order by r.sigungu_code) as regions,
               n.detail_url
        from notice.notices m
        join notice.notices n on n.id = coalesce(m.merged_into, m.id)
        where m.id in (:ids) and n.current_version > 0 and not n.hidden
        """,
        new MapSqlParameterSource("ids", ids),
        (rs, i) ->
            new SummaryRow(
                rs.getObject(1, UUID.class),
                rs.getObject(2, UUID.class),
                rs.getInt(3),
                rs.getString(4),
                rs.getString(5),
                rs.getString(6),
                rs.getString(7),
                rs.getString(8),
                rs.getObject(9, LocalDate.class),
                rs.getObject(10, LocalDate.class),
                rs.getBoolean(11),
                List.of((String[]) rs.getArray(12).getArray()),
                rs.getString(13)));
  }

  /**
   * 마감일이 dates 중 하나이고 오늘 접수 중인 공고 ID (마감 D-3·D-1 알림용). 숨김·공개 전·다른 공고에 합쳐진 공고·아직 시작 전인 공고는 빼요. 상태 칸
   * 대신 날짜로 골라서 상태 재계산이 늦어도 결과가 같아요.
   */
  public List<UUID> openClosingOn(java.util.Collection<LocalDate> dates, LocalDate today) {
    if (dates.isEmpty()) {
      return List.of();
    }
    return jdbc.queryForList(
        """
        select id from notice.notices
        where merged_into is null and current_version > 0 and not hidden
          and apply_end in (:dates) and (apply_start is null or apply_start <= :today)
        order by apply_end, id
        """,
        new MapSqlParameterSource("dates", List.copyOf(dates)).addValue("today", today),
        UUID.class);
  }

  /** 공개 버전 하나 (정정 이력). 글 종류는 payload에서 읽어요. */
  public record VersionRow(
      int version, String reviewStatus, OffsetDateTime receivedAt, String payload) {}

  /** 공개된 버전들을 버전 순서로. 숨김·공개 전·없는 공고면 빈 목록. */
  public List<VersionRow> versions(UUID noticeId) {
    return jdbc.query(
        """
        select v.version, v.review_status, v.created_at, v.payload::text
        from notice.notice_versions v join notice.notices n on n.id = v.notice_id
        where v.notice_id = coalesce((select m.merged_into from notice.notices m where m.id = :id), :id)
          and n.current_version > 0 and not n.hidden
        order by v.version
        """,
        new MapSqlParameterSource("id", noticeId),
        (rs, i) ->
            new VersionRow(
                rs.getInt(1),
                rs.getString(2),
                rs.getObject(3, OffsetDateTime.class),
                rs.getString(4)));
  }

  /** 커서에 넣을 정렬 값 (목록의 정렬 식과 같아야 해요). */
  public static String sortValue(ListRow row, String sort) {
    if ("LATEST".equals(sort)) {
      return (row.postedOn() == null ? NO_POSTED : row.postedOn()).toString();
    }
    return (row.applyEnd() == null ? NO_END : row.applyEnd()).toString();
  }
}
