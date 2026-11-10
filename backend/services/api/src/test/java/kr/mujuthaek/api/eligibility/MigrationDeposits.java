package kr.mujuthaek.api.eligibility;

import java.io.IOException;
import java.math.BigDecimal;
import java.net.URISyntaxException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;
import java.util.OptionalLong;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.stream.Stream;
import kr.mujuthaek.api.eligibility.rule.DepositRegion;
import kr.mujuthaek.api.eligibility.rule.SubscriptionDeposits;

/** 테스트용 예치기준금액: 마이그레이션 SQL의 subscription_deposits 행을 그대로 읽어요. DB 없이도 실제로 넣은 숫자로 판정을 돌리려고요. */
public final class MigrationDeposits implements SubscriptionDeposits {

  private static final Pattern ROW =
      Pattern.compile(
          "\\('[0-9a-f-]{36}',\\s*'(\\d{4}-\\d{2}-\\d{2})',\\s*'(\\w+)',\\s*(\\d+(?:\\.\\d+)?|null),\\s*(\\d+),");

  private final List<Row> rows;

  private MigrationDeposits(List<Row> rows) {
    this.rows = List.copyOf(rows);
  }

  public static MigrationDeposits load() {
    List<Row> rows = new ArrayList<>();
    try (Stream<Path> files =
        Files.list(Path.of(MigrationDeposits.class.getResource("/db/migration").toURI()))) {
      for (Path file :
          files.filter(f -> f.getFileName().toString().contains("__eligibility_")).toList()) {
        String sql = Files.readString(file);
        if (!sql.contains("subscription_deposits")) {
          continue;
        }
        Matcher m = ROW.matcher(sql);
        while (m.find()) {
          rows.add(
              new Row(
                  LocalDate.parse(m.group(1)),
                  DepositRegion.valueOf(m.group(2)),
                  "null".equals(m.group(3)) ? null : new BigDecimal(m.group(3)).setScale(2),
                  Long.parseLong(m.group(4))));
        }
      }
    } catch (IOException | URISyntaxException e) {
      throw new IllegalStateException("마이그레이션 파일을 읽지 못했어요", e);
    }
    return new MigrationDeposits(rows);
  }

  public List<Row> rows() {
    return rows;
  }

  @Override
  public OptionalLong find(LocalDate day, DepositRegion region, BigDecimal exclusiveAreaM2) {
    return SubscriptionDeposits.pick(rows, day, region, exclusiveAreaM2);
  }
}
