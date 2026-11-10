package kr.mujuthaek.api.benefit.repository;

import java.sql.Array;
import java.sql.Date;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Timestamp;
import java.time.Instant;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collection;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import kr.mujuthaek.api.benefit.domain.BenefitStatus;
import kr.mujuthaek.api.benefit.mapper.PolicyExtractedEvent;
import kr.mujuthaek.api.benefit.mapper.PolicyExtractedEvent.Condition;
import kr.mujuthaek.api.benefit.mapper.PolicyExtractedEvent.Support;
import kr.mujuthaek.api.common.id.UuidV7;
import kr.mujuthaek.api.common.region.CityDistricts;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

/** 혜택 읽기·쓰기 (benefit.benefits + benefit_supports + benefit_conditions). */
@Repository
public class BenefitRepository {

  private final JdbcClient jdbc;

  public BenefitRepository(JdbcClient jdbc) {
    this.jdbc = jdbc;
  }

  /** 저장된 혜택의 ID, 반영한 수집 버전, 범위 안(보이는 혜택)인지. */
  public record Saved(UUID id, int version, boolean relevant) {}

  /** 다른 모듈(알림)에 주는 혜택 요약 한 줄. */
  public record SummaryRow(
      UUID id,
      String field,
      int version,
      String title,
      String agency,
      String status,
      LocalDate applyStart,
      LocalDate applyEnd,
      boolean applyAlways,
      String regionScope,
      List<String> regionCodes,
      String detailUrl) {}

  /** 혜택 한 줄 (지원 내용·조건 포함). */
  public record Row(
      UUID id,
      String sourceCode,
      String field,
      String category,
      String title,
      String agency,
      String regionScope,
      List<String> regionNames,
      List<String> regionCodes,
      List<String> categories,
      String detailUrl,
      String applyUrl,
      String summary,
      LocalDate applyStart,
      LocalDate applyEnd,
      boolean applyAlways,
      LocalDate businessStart,
      LocalDate businessEnd,
      String scheduleText,
      String howToApply,
      List<String> documents,
      String contact,
      String status,
      boolean needsReview,
      List<Support> supports,
      List<Condition> conditions,
      Instant updatedAt) {}

  public Optional<Saved> findByRawPolicyId(UUID rawPolicyId) {
    return jdbc.sql(
            "select id, source_version, relevant from benefit.benefits where raw_policy_id = ?")
        .param(rawPolicyId)
        .query(
            (rs, i) ->
                new Saved(
                    rs.getObject("id", UUID.class),
                    rs.getInt("source_version"),
                    rs.getBoolean("relevant")))
        .optional();
  }

  /** 새로 넣거나(id가 없으면) 고쳐요. 지원 내용·조건 줄은 지우고 다시 넣어요 (줄 단위 비교는 하지 않아요). */
  public UUID save(
      UUID id, PolicyExtractedEvent e, String category, BenefitStatus status, Instant now) {
    UUID benefitId = id == null ? UuidV7.next() : id;
    jdbc.sql(
            "insert into benefit.benefits (id, raw_policy_id, source_code, provider, source_policy_id,"
                + " source_version, field, category, title, agency, region_scope, region_names,"
                + " region_codes, categories, detail_url, apply_url, summary, apply_start, apply_end,"
                + " apply_always, business_start, business_end, schedule_text, how_to_apply,"
                + " documents, contact, status, relevant, confidence, needs_review, review_reasons,"
                + " has_document, extracted_at, created_at, updated_at) values (:id, :raw, :source,"
                + " :provider, :policyId, :version, :field, :category, :title, :agency, :scope,"
                + " cast(:regionNames as text[]), cast(:regionCodes as text[]),"
                + " cast(:categories as text[]), :detailUrl, :applyUrl, :summary, :applyStart,"
                + " :applyEnd, :applyAlways, :businessStart, :businessEnd, :scheduleText,"
                + " :howToApply, cast(:documents as text[]), :contact, :status, :relevant,"
                + " :confidence, :needsReview, cast(:reviewReasons as text[]), :hasDocument,"
                + " :extractedAt, :now, :now) on conflict (raw_policy_id) do update set"
                + " source_code = excluded.source_code, provider = excluded.provider,"
                + " source_policy_id = excluded.source_policy_id,"
                + " source_version = excluded.source_version, field = excluded.field,"
                + " category = excluded.category, title = excluded.title, agency = excluded.agency,"
                + " region_scope = excluded.region_scope, region_names = excluded.region_names,"
                + " region_codes = excluded.region_codes, categories = excluded.categories,"
                + " detail_url = excluded.detail_url, apply_url = excluded.apply_url,"
                + " summary = excluded.summary, apply_start = excluded.apply_start,"
                + " apply_end = excluded.apply_end, apply_always = excluded.apply_always,"
                + " business_start = excluded.business_start, business_end = excluded.business_end,"
                + " schedule_text = excluded.schedule_text, how_to_apply = excluded.how_to_apply,"
                + " documents = excluded.documents, contact = excluded.contact,"
                + " status = excluded.status, relevant = excluded.relevant,"
                + " confidence = excluded.confidence, needs_review = excluded.needs_review,"
                + " review_reasons = excluded.review_reasons, has_document = excluded.has_document,"
                + " extracted_at = excluded.extracted_at, updated_at = excluded.updated_at")
        .param("id", benefitId)
        .param("raw", e.rawPolicyId())
        .param("source", e.sourceCode())
        .param("provider", e.provider())
        .param("policyId", e.policyId())
        .param("version", e.version())
        .param("field", e.field())
        .param("category", category)
        .param("title", e.title())
        .param("agency", e.agency())
        .param("scope", e.regionScope())
        .param("regionNames", e.regionNames().toArray(String[]::new))
        .param("regionCodes", e.regionCodes().toArray(String[]::new))
        .param("categories", e.categories().toArray(String[]::new))
        .param("detailUrl", e.detailUrl())
        .param("applyUrl", e.applyUrl())
        .param("summary", e.summary())
        .param("applyStart", e.applyStart())
        .param("applyEnd", e.applyEnd())
        .param("applyAlways", e.applyAlways())
        .param("businessStart", e.businessStart())
        .param("businessEnd", e.businessEnd())
        .param("scheduleText", e.scheduleText())
        .param("howToApply", e.howToApply())
        .param("documents", e.documents().toArray(String[]::new))
        .param("contact", e.contact())
        .param("status", status.name())
        .param("relevant", e.relevant())
        .param("confidence", e.confidence())
        .param("needsReview", e.needsReview())
        .param("reviewReasons", e.reviewReasons().toArray(String[]::new))
        .param("hasDocument", e.hasDocument())
        .param("extractedAt", Timestamp.from(e.extractedAt()))
        .param("now", Timestamp.from(now))
        .update();
    jdbc.sql("delete from benefit.benefit_supports where benefit_id = ?").param(benefitId).update();
    jdbc.sql("delete from benefit.benefit_conditions where benefit_id = ?")
        .param(benefitId)
        .update();
    for (int i = 0; i < e.supports().size(); i++) {
      Support s = e.supports().get(i);
      jdbc.sql(
              "insert into benefit.benefit_supports (id, benefit_id, ordinal, kind, amount_max,"
                  + " amount_per, months, rate_pct, raw_text, evidence) values (?, ?, ?, ?, ?, ?, ?,"
                  + " ?, ?, ?)")
          .params(
              UuidV7.next(),
              benefitId,
              i,
              s.kind(),
              s.amountMax(),
              s.amountPer(),
              s.months(),
              s.ratePct(),
              s.rawText(),
              s.evidence())
          .update();
    }
    for (int i = 0; i < e.conditions().size(); i++) {
      Condition c = e.conditions().get(i);
      jdbc.sql(
              "insert into benefit.benefit_conditions (id, benefit_id, ordinal, type, value, grp,"
                  + " known, raw_text, evidence, confidence, origin) values (?, ?, ?, ?,"
                  + " cast(? as jsonb), ?, ?, ?, ?, ?, ?)")
          .params(
              UuidV7.next(),
              benefitId,
              i,
              c.type(),
              c.valueJson(),
              c.group(),
              c.known(),
              c.rawText(),
              c.evidence(),
              c.confidence(),
              c.origin())
          .update();
    }
    return benefitId;
  }

  /** 상태를 다시 계산할 혜택 (숨김 빼고). */
  public record StatusRow(
      UUID id, String status, boolean applyAlways, LocalDate applyStart, LocalDate applyEnd) {}

  public List<StatusRow> visibleStatuses() {
    return jdbc.sql(
            "select id, status, apply_always, apply_start, apply_end from benefit.benefits"
                + " where status <> 'HIDDEN'")
        .query(
            (rs, i) ->
                new StatusRow(
                    rs.getObject("id", UUID.class),
                    rs.getString("status"),
                    rs.getBoolean("apply_always"),
                    day(rs, "apply_start"),
                    day(rs, "apply_end")))
        .list();
  }

  public void updateStatus(UUID id, BenefitStatus status, Instant now) {
    jdbc.sql("update benefit.benefits set status = ?, updated_at = ? where id = ?")
        .params(status.name(), Timestamp.from(now), id)
        .update();
  }

  /**
   * 판정 후보: 숨김·마감을 빼고, regionCodes가 있으면 전국 혜택 + 그 지역과 겹치는 혜택만 (시도 2자리는 그 안 시군구와 겹쳐요). field는
   * BENEFIT만.
   */
  public List<Row> openBenefits(Collection<String> regionCodes) {
    return openBenefits(regionCodes, r -> false);
  }

  /**
   * {@link #openBenefits(Collection)}과 같되, skipLines가 참인 혜택(판정 캐시에 같은 수정 시각으로 이미 있는 것)은 지원 내용·조건을
   * 읽지 않아요.
   *
   * <p>판정에 쓰는 칸만 읽어요(설명·서류·신청 방법 같은 긴 칸은 빼요: 한 줄 약 940바이트 → 판정 칸). 나이로 지원 불가를 DB에서 미리 거르던 하위 쿼리는
   * 뺐어요: 혜택마다 조건을 다시 훑어 요청마다 DB 시간이 20ms 넘게 늘고 그동안 커넥션을 쥐었는데, 조건은 이제 앱이 캐시해 두고 판정하므로 얻는 게
   * 없었어요(2026-11-02 로컬 실행 계획: 32~55ms → 12ms). 판정 결과는 같아요(BenefitJudge가 같은 규칙으로 판정해요).
   */
  public List<Row> openBenefits(
      Collection<String> regionCodes, java.util.function.Predicate<Row> skipLines) {
    String[] regions = regionCodes.toArray(String[]::new);
    List<Row> rows =
        jdbc.sql(
                "select "
                    + JUDGMENT_COLUMNS
                    + " from benefit.benefits b where b.field = 'BENEFIT'"
                    + " and b.status in ('UPCOMING', 'OPEN') and (cardinality(cast(:regions as"
                    + " text[])) = 0 or b.region_scope = 'NATIONWIDE' or exists (select 1 from"
                    + " unnest(b.region_codes) r, unnest(cast(:regions as text[])) f where r like f"
                    + " || '%' or f like r || '%' or "
                    // 일반구가 있는 시와 그 구도 겹쳐요(재검토: 장안구 회원에게 수원시 혜택이 후보에서 빠졌음)
                    + CityDistricts.sqlInCity("f", "r")
                    + " or "
                    + CityDistricts.sqlInCity("r", "f")
                    + ")) order by b.apply_end nulls last, b.id")
            .param("regions", regions)
            .query(BenefitRepository::judgmentRow)
            .list();
    java.util.Set<UUID> skip = new java.util.HashSet<>();
    rows.stream().filter(skipLines).forEach(r -> skip.add(r.id()));
    return withLines(rows, skip);
  }

  /** 판정(BenefitQueryService.toJudgment)에 쓰는 칸. */
  private static final String JUDGMENT_COLUMNS =
      "b.id, b.source_code, b.field, b.category, b.title, b.agency, b.region_scope, b.region_names,"
          + " b.region_codes, b.summary, b.apply_start, b.apply_end, b.apply_always, b.status,"
          + " b.needs_review, b.updated_at";

  /** 판정 칸만 읽은 줄. 상세 화면 칸(설명·서류·신청 방법 …)은 비어 있어요. */
  private static Row judgmentRow(ResultSet rs, int i) throws SQLException {
    return new Row(
        rs.getObject("id", UUID.class),
        rs.getString("source_code"),
        rs.getString("field"),
        rs.getString("category"),
        rs.getString("title"),
        rs.getString("agency"),
        rs.getString("region_scope"),
        strings(rs.getArray("region_names")),
        strings(rs.getArray("region_codes")),
        List.of(),
        null,
        null,
        rs.getString("summary"),
        day(rs, "apply_start"),
        day(rs, "apply_end"),
        rs.getBoolean("apply_always"),
        null,
        null,
        null,
        null,
        List.of(),
        null,
        rs.getString("status"),
        rs.getBoolean("needs_review"),
        List.of(),
        List.of(),
        rs.getTimestamp("updated_at").toInstant());
  }

  public Optional<Row> find(UUID id) {
    List<Row> rows =
        jdbc.sql("select * from benefit.benefits where id = ? and status <> 'HIDDEN'")
            .param(id)
            .query(BenefitRepository::row)
            .list();
    return withLines(rows, java.util.Set.of()).stream().findFirst();
  }

  /** 혜택 하나의 요약 (숨김 포함). */
  /** 혜택 ID → 정책 원본 ID (rawPolicyId) */
  public Optional<UUID> rawPolicyId(UUID id) {
    return jdbc.sql("select raw_policy_id from benefit.benefits where id = ?")
        .param(id)
        .query(UUID.class)
        .optional();
  }

  public Optional<SummaryRow> summary(UUID id) {
    return jdbc.sql(SUMMARY + " where id = ?")
        .param(id)
        .query(BenefitRepository::summary)
        .optional();
  }

  /** 혜택 여러 개의 요약을 한 번에 (숨김 포함, 없는 ID는 빠져요). 관심 목록이 한 줄씩 묻지 않게요. */
  public List<SummaryRow> summaries(Collection<UUID> ids) {
    if (ids.isEmpty()) return List.of();
    return jdbc.sql(SUMMARY + " where id = any(?)")
        .param(ids.toArray(UUID[]::new))
        .query(BenefitRepository::summary)
        .list();
  }

  /** 수집 정책 ID로 혜택 하나의 요약 (숨김 포함). */
  public Optional<SummaryRow> summaryByRawPolicyId(UUID rawPolicyId) {
    return jdbc.sql(SUMMARY + " where raw_policy_id = ?")
        .param(rawPolicyId)
        .query(BenefitRepository::summary)
        .optional();
  }

  /** 마감일이 dates 중 하나이고 오늘 접수 중인 혜택 (숨김·상시·시작 전 제외). 상태 칸 대신 날짜로 골라요 (상태 재계산이 늦어도 같게) */
  public List<SummaryRow> openClosingOn(Collection<LocalDate> dates, LocalDate today) {
    if (dates.isEmpty()) return List.of();
    return jdbc.sql(
            SUMMARY
                + " where relevant and not apply_always and apply_end = any(?)"
                + " and (apply_start is null or apply_start <= ?) order by apply_end, id")
        .params(dates.stream().map(Date::valueOf).toArray(Date[]::new), Date.valueOf(today))
        .query(BenefitRepository::summary)
        .list();
  }

  private static final String SUMMARY =
      "select id, field, source_version, title, agency, status, apply_start, apply_end,"
          + " apply_always, region_scope, region_codes, detail_url from benefit.benefits";

  private static SummaryRow summary(ResultSet rs, int i) throws SQLException {
    return new SummaryRow(
        rs.getObject("id", UUID.class),
        rs.getString("field"),
        rs.getInt("source_version"),
        rs.getString("title"),
        rs.getString("agency"),
        rs.getString("status"),
        day(rs, "apply_start"),
        day(rs, "apply_end"),
        rs.getBoolean("apply_always"),
        rs.getString("region_scope"),
        strings(rs.getArray("region_codes")),
        rs.getString("detail_url"));
  }

  /** 지원 내용·조건 줄을 한 번에 읽어 붙여요 (혜택 수만큼 질의하지 않게). skip의 혜택은 읽지 않고 비워 둬요. */
  private List<Row> withLines(List<Row> rows, java.util.Set<UUID> skip) {
    if (rows.isEmpty()) return rows;
    UUID[] ids = rows.stream().map(Row::id).filter(id -> !skip.contains(id)).toArray(UUID[]::new);
    Map<UUID, List<Support>> supports = new LinkedHashMap<>();
    jdbc.sql(
            "select * from benefit.benefit_supports where benefit_id = any(?) order by benefit_id,"
                + " ordinal")
        .param(ids)
        .query(
            rs -> {
              supports
                  .computeIfAbsent(rs.getObject("benefit_id", UUID.class), k -> new ArrayList<>())
                  .add(
                      new Support(
                          rs.getString("kind"),
                          (Integer) rs.getObject("amount_max"),
                          rs.getString("amount_per"),
                          (Integer) rs.getObject("months"),
                          rs.getBigDecimal("rate_pct"),
                          rs.getString("raw_text"),
                          rs.getString("evidence")));
            });
    Map<UUID, List<Condition>> conditions = new LinkedHashMap<>();
    jdbc.sql(
            "select * from benefit.benefit_conditions where benefit_id = any(?) order by"
                + " benefit_id, ordinal")
        .param(ids)
        .query(
            rs -> {
              conditions
                  .computeIfAbsent(rs.getObject("benefit_id", UUID.class), k -> new ArrayList<>())
                  .add(
                      new Condition(
                          rs.getString("type"),
                          rs.getString("value"),
                          rs.getInt("grp"),
                          rs.getBoolean("known"),
                          rs.getString("raw_text"),
                          rs.getString("evidence"),
                          rs.getDouble("confidence"),
                          rs.getString("origin")));
            });
    return rows.stream()
        .map(
            r ->
                new Row(
                    r.id(),
                    r.sourceCode(),
                    r.field(),
                    r.category(),
                    r.title(),
                    r.agency(),
                    r.regionScope(),
                    r.regionNames(),
                    r.regionCodes(),
                    r.categories(),
                    r.detailUrl(),
                    r.applyUrl(),
                    r.summary(),
                    r.applyStart(),
                    r.applyEnd(),
                    r.applyAlways(),
                    r.businessStart(),
                    r.businessEnd(),
                    r.scheduleText(),
                    r.howToApply(),
                    r.documents(),
                    r.contact(),
                    r.status(),
                    r.needsReview(),
                    supports.getOrDefault(r.id(), List.of()),
                    conditions.getOrDefault(r.id(), List.of()),
                    r.updatedAt()))
        .toList();
  }

  private static Row row(ResultSet rs, int i) throws SQLException {
    return new Row(
        rs.getObject("id", UUID.class),
        rs.getString("source_code"),
        rs.getString("field"),
        rs.getString("category"),
        rs.getString("title"),
        rs.getString("agency"),
        rs.getString("region_scope"),
        strings(rs.getArray("region_names")),
        strings(rs.getArray("region_codes")),
        strings(rs.getArray("categories")),
        rs.getString("detail_url"),
        rs.getString("apply_url"),
        rs.getString("summary"),
        day(rs, "apply_start"),
        day(rs, "apply_end"),
        rs.getBoolean("apply_always"),
        day(rs, "business_start"),
        day(rs, "business_end"),
        rs.getString("schedule_text"),
        rs.getString("how_to_apply"),
        strings(rs.getArray("documents")),
        rs.getString("contact"),
        rs.getString("status"),
        rs.getBoolean("needs_review"),
        List.of(),
        List.of(),
        rs.getTimestamp("updated_at").toInstant());
  }

  private static LocalDate day(ResultSet rs, String column) throws SQLException {
    Date d = rs.getDate(column);
    return d == null ? null : d.toLocalDate();
  }

  private static List<String> strings(Array array) throws SQLException {
    return array == null ? List.of() : Arrays.asList((String[]) array.getArray());
  }
}
