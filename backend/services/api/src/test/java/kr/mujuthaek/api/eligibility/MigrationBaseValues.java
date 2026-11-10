package kr.mujuthaek.api.eligibility;

import java.io.IOException;
import java.net.URISyntaxException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HashMap;
import java.util.Map;
import java.util.OptionalLong;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.stream.Stream;
import kr.mujuthaek.api.eligibility.rule.BaseValueKind;
import kr.mujuthaek.api.eligibility.rule.BaseValues;

/** 테스트용 기준값: 마이그레이션 SQL의 기준값 행을 그대로 읽어요. DB 없이도 실제로 넣은 숫자로 정답 케이스를 돌리려고요. */
final class MigrationBaseValues implements BaseValues {

  private static final Pattern ROW =
      Pattern.compile(
          "\\('[0-9a-f-]{36}',\\s*'(\\w+)',\\s*(\\d{4}),\\s*'([^']*)',\\s*(\\d+),\\s*(\\d+),");

  private final Map<String, Map<Integer, Long>> tables = new HashMap<>();

  static MigrationBaseValues load() {
    MigrationBaseValues values = new MigrationBaseValues();
    try (Stream<Path> files =
        Files.list(Path.of(MigrationBaseValues.class.getResource("/db/migration").toURI()))) {
      for (Path file :
          files.filter(f -> f.getFileName().toString().contains("__eligibility_")).toList()) {
        Matcher m = ROW.matcher(Files.readString(file));
        while (m.find()) {
          values
              .tables
              .computeIfAbsent(
                  key(BaseValueKind.valueOf(m.group(1)), Integer.parseInt(m.group(2)), m.group(3)),
                  k -> new HashMap<>())
              .put(Integer.parseInt(m.group(4)), Long.parseLong(m.group(5)));
        }
      }
    } catch (IOException | URISyntaxException e) {
      throw new IllegalStateException("마이그레이션 파일을 읽지 못했어요", e);
    }
    return values;
  }

  int size() {
    return tables.values().stream().mapToInt(Map::size).sum();
  }

  @Override
  public OptionalLong find(BaseValueKind kind, int year, String program, int householdSize) {
    Map<Integer, Long> table = tables.getOrDefault(key(kind, year, program), Map.of());
    if (!kind.byHouseholdSize()) {
      return table.values().stream().mapToLong(Long::longValue).findFirst();
    }
    return BaseValues.byHouseholdSize(table, householdSize);
  }

  private static String key(BaseValueKind kind, int year, String program) {
    return kind + "/" + year + "/" + program;
  }
}
