package kr.mujuthaek.api.common.region;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.StringReader;
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.Charset;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Date;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.core.io.Resource;
import org.springframework.core.io.support.PathMatchingResourcePatternResolver;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

/**
 * 법정동코드 전체자료로 common.regions를 채워요. 같은 파일을 다시 넣어도 결과가 같아요(코드 기준으로 덮어씀).
 *
 * <p>원본은 저장소의 법정동코드표(services/extraction/data/legal-dong-codes, 빌드 때 리소스 common/regions/로 복사)예요. 파일
 * 이름의 날짜(legal_dong_20260929.csv)가 기준일이에요. 따로 받은 파일(탭 구분, CP949)도 경로로 넣을 수 있어요.
 *
 * <p>폐지된 코드는 지우지 않고 valid = false로 두고, 같은 시도(짧은 이름 기준) 안에 이름이 같은 유효한 코드가 있으면 그 코드를 replaced_by로
 * 이어요. 예: 강원도 춘천시(42110, 폐지) → 강원특별자치도 춘천시(51110).
 */
@Component
public class RegionLoader {

  private static final Logger log = LoggerFactory.getLogger(RegionLoader.class);
  static final Charset CP949 = Charset.forName("MS949");
  static final String BUNDLED = "classpath*:common/regions/legal_dong_*.csv";
  private static final Pattern BUNDLED_DATE = Pattern.compile("legal_dong_(\\d{8})\\.csv$");

  private final JdbcTemplate jdbc;

  public RegionLoader(JdbcTemplate jdbc) {
    this.jdbc = jdbc;
  }

  /**
   * @return 넣거나 고친 시도·시군구 수
   */
  @Transactional
  public int load(Path file, LocalDate baseDate) throws IOException {
    return load(decode(Files.readAllBytes(file)), baseDate);
  }

  /** 빌드에 들어간 저장소 법정동코드표 중 가장 최근 것. */
  public static Bundled bundled() throws IOException {
    Resource latest =
        Arrays.stream(new PathMatchingResourcePatternResolver().getResources(BUNDLED))
            .filter(r -> r.getFilename() != null && BUNDLED_DATE.matcher(r.getFilename()).find())
            .max(Comparator.comparing(Resource::getFilename))
            .orElseThrow(() -> new IllegalStateException("법정동코드표 리소스가 없어요: " + BUNDLED));
    Matcher date = BUNDLED_DATE.matcher(latest.getFilename());
    date.find();
    String text = new String(latest.getContentAsByteArray(), StandardCharsets.UTF_8);
    return new Bundled(
        latest.getFilename(),
        LocalDate.parse(date.group(1), DateTimeFormatter.BASIC_ISO_DATE),
        text);
  }

  /** 저장소 법정동코드표 한 판. */
  public record Bundled(String fileName, LocalDate baseDate, String text) {}

  @Transactional
  public int loadBundled() throws IOException {
    Bundled bundled = bundled();
    return load(bundled.text(), bundled.baseDate());
  }

  private int load(String text, LocalDate baseDate) throws IOException {
    List<RegionCodeFile.Entry> entries;
    try (BufferedReader reader = new BufferedReader(new StringReader(text))) {
      entries = RegionCodeFile.entries(reader);
    }
    List<RegionCodeFile.Row> rows = RegionCodeFile.rows(entries);
    // 시도부터 넣어야 시군구의 상위 코드가 맞아요
    rows.stream().filter(r -> r.level().equals("SIDO")).forEach(r -> upsert(r, baseDate));
    rows.stream().filter(r -> r.level().equals("SIGUNGU")).forEach(r -> upsert(r, baseDate));
    linkReplacements();
    List<RegionCodeChanges.Change> changes = RegionCodeChanges.compute(entries);
    saveChanges(changes, baseDate);
    log.info(
        "지역 코드 적재: 시도·시군구 {}개, 예전 → 지금 코드 {}개 (기준일 {})", rows.size(), changes.size(), baseDate);
    return rows.size();
  }

  /** UTF-8로 읽히면 UTF-8(저장소 원본), 아니면 CP949(행정표준코드관리시스템에서 받은 파일). */
  static String decode(byte[] bytes) {
    try {
      return StandardCharsets.UTF_8
          .newDecoder()
          .onMalformedInput(CodingErrorAction.REPORT)
          .onUnmappableCharacter(CodingErrorAction.REPORT)
          .decode(ByteBuffer.wrap(bytes))
          .toString()
          .replace("\uFEFF", "");
    } catch (CharacterCodingException e) {
      return new String(bytes, CP949);
    }
  }

  private void upsert(RegionCodeFile.Row r, LocalDate baseDate) {
    jdbc.update(
        """
        insert into common.regions (code, level, parent_code, name, full_name, short_name, valid, base_date)
        values (?, ?, ?, ?, ?, ?, ?, ?)
        on conflict (code) do update
          set level = excluded.level, parent_code = excluded.parent_code, name = excluded.name,
              full_name = excluded.full_name, short_name = excluded.short_name, valid = excluded.valid,
              base_date = excluded.base_date, updated_at = now()
        """,
        r.code(),
        r.level(),
        r.parentCode(),
        r.name(),
        r.fullName(),
        r.shortName(),
        r.valid(),
        Date.valueOf(baseDate));
  }

  /** 예전 → 지금 코드 대응표를 새로 채우고, 새 코드가 하나로 정해지는 시도·시군구는 replaced_by로도 이어요. */
  private void saveChanges(List<RegionCodeChanges.Change> changes, LocalDate baseDate) {
    jdbc.update("delete from common.region_code_changes");
    jdbc.batchUpdate(
        "insert into common.region_code_changes (old_code, new_code, base_date) values (?, ?, ?)",
        changes,
        1000,
        (ps, c) -> {
          ps.setString(1, c.oldCode());
          ps.setString(2, c.newCode());
          ps.setDate(3, Date.valueOf(baseDate));
        });
    // 10자리 → common.regions 코드: 시도 2자리(XX00000000), 시군구 5자리(XXXXX00000)
    jdbc.update(
        """
        with one as (
          select old_code, min(new_code) as new_code from common.region_code_changes
          where old_code like '%00000' group by old_code having count(*) = 1
        ), short as (
          select case when old_code like '%00000000' then left(old_code, 2) else left(old_code, 5) end as old,
                 case when new_code like '%00000000' then left(new_code, 2) else left(new_code, 5) end as new
          from one
        )
        update common.regions r set replaced_by = s.new
        from short s
        where r.code = s.old and not r.valid
          and exists (select 1 from common.regions n where n.code = s.new and n.valid)
        """);
  }

  private void linkReplacements() {
    // 시도: 같은 짧은 이름의 유효한 시도 (강원 42 → 51, 전북 45 → 52)
    jdbc.update(
        """
        update common.regions old set replaced_by = cur.code
        from common.regions cur
        where old.level = 'SIDO' and cur.level = 'SIDO' and not old.valid and cur.valid
          and old.short_name = cur.short_name and old.code <> cur.code
        """);
    // 시군구: 상위 시도의 짧은 이름과 시군구 이름이 같은 유효한 시군구
    jdbc.update(
        """
        update common.regions old set replaced_by = cur.code
        from common.regions cur, common.regions old_sido, common.regions cur_sido
        where old.level = 'SIGUNGU' and cur.level = 'SIGUNGU' and not old.valid and cur.valid
          and old.parent_code = old_sido.code and cur.parent_code = cur_sido.code
          and old_sido.short_name = cur_sido.short_name and old.name = cur.name and old.code <> cur.code
        """);
  }
}
