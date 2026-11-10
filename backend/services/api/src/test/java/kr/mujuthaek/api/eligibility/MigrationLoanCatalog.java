package kr.mujuthaek.api.eligibility;

import java.io.IOException;
import java.net.URISyntaxException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Stream;
import kr.mujuthaek.api.eligibility.rule.loan.LoanCatalog;
import kr.mujuthaek.api.eligibility.rule.loan.LoanTerms;
import kr.mujuthaek.api.eligibility.rule.loan.LoanType;

/** 테스트용 대출 상품 조건: 마이그레이션 SQL의 loan_rules 행을 그대로 읽어요. DB 없이도 실제로 넣은 숫자로 판정을 돌리려고요. */
public final class MigrationLoanCatalog implements LoanCatalog {

  private final List<LoanTerms> rows;

  private MigrationLoanCatalog(List<LoanTerms> rows) {
    this.rows = List.copyOf(rows);
  }

  public static MigrationLoanCatalog load() {
    List<LoanTerms> rows = new ArrayList<>();
    try (Stream<Path> files =
        Files.list(Path.of(MigrationLoanCatalog.class.getResource("/db/migration").toURI()))) {
      for (Path file :
          files.filter(f -> f.getFileName().toString().contains("__eligibility_")).toList()) {
        String sql = Files.readString(file);
        int insert = sql.indexOf("insert into eligibility.loan_rules");
        if (insert < 0) {
          continue;
        }
        String body = sql.substring(sql.indexOf(") values", insert) + ") values".length());
        for (String tuple : tuples(body)) {
          rows.add(terms(values(tuple)));
        }
      }
    } catch (IOException | URISyntaxException e) {
      throw new IllegalStateException("마이그레이션 파일을 읽지 못했어요", e);
    }
    return new MigrationLoanCatalog(rows);
  }

  public List<LoanTerms> rows() {
    return rows;
  }

  @Override
  public List<LoanTerms> asOf(LocalDate day) {
    return LoanCatalog.latest(rows, day);
  }

  /** values 뒤의 (…), (…); 를 행마다 나눠요. 작은따옴표 안의 괄호·쉼표는 글자로 봐요. */
  private static List<String> tuples(String body) {
    List<String> tuples = new ArrayList<>();
    StringBuilder current = new StringBuilder();
    boolean quoted = false;
    int depth = 0;
    for (char c : body.toCharArray()) {
      if (c == '\'') {
        quoted = !quoted;
      }
      if (!quoted && c == '(') {
        if (depth++ == 0) {
          current.setLength(0);
          continue;
        }
      }
      if (!quoted && c == ')') {
        if (--depth == 0) {
          tuples.add(current.toString());
          continue;
        }
      }
      if (!quoted && depth == 0 && c == ';') {
        break;
      }
      if (depth > 0) {
        current.append(c);
      }
    }
    return tuples;
  }

  /** SQL 값 목록을 쉼표로 나눠요. 작은따옴표 안의 쉼표는 나누지 않아요. */
  private static List<String> values(String tuple) {
    List<String> values = new ArrayList<>();
    StringBuilder current = new StringBuilder();
    boolean quoted = false;
    for (char c : tuple.toCharArray()) {
      if (c == '\'') {
        quoted = !quoted;
      } else if (c == ',' && !quoted) {
        values.add(current.toString().trim());
        current.setLength(0);
        continue;
      }
      current.append(c);
    }
    values.add(current.toString().trim());
    return values;
  }

  private static LoanTerms terms(List<String> v) {
    // 열 순서는 마이그레이션 insert 문과 같아요 (0번은 id)
    return new LoanTerms(
        text(v.get(1)),
        text(v.get(2)),
        LoanType.valueOf(text(v.get(3))),
        Integer.parseInt(v.get(4)),
        LocalDate.parse(text(v.get(5))),
        integer(v.get(6)),
        integer(v.get(7)),
        Boolean.parseBoolean(v.get(8)),
        Boolean.parseBoolean(v.get(9)),
        Boolean.parseBoolean(v.get(10)),
        integer(v.get(11)),
        integer(v.get(12)),
        "null".equals(v.get(13)) ? null : LocalDate.parse(text(v.get(13))),
        Boolean.parseBoolean(v.get(14)),
        Long.parseLong(v.get(15)),
        number(v.get(16)),
        number(v.get(17)),
        number(v.get(18)),
        number(v.get(19)),
        number(v.get(20)),
        number(v.get(21)),
        Long.parseLong(v.get(22)),
        "null".equals(v.get(23)) ? null : text(v.get(23)),
        text(v.get(24)),
        text(v.get(25)),
        text(v.get(26)));
  }

  private static String text(String value) {
    return value.substring(1, value.length() - 1);
  }

  private static Integer integer(String value) {
    return "null".equals(value) ? null : Integer.valueOf(value);
  }

  private static Long number(String value) {
    return "null".equals(value) ? null : Long.valueOf(value);
  }
}
