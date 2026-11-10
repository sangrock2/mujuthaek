package kr.mujuthaek.api.area.geocode;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.BufferedReader;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import kr.mujuthaek.api.area.geocode.ParsedAddress.Kind;
import org.junit.jupiter.api.Test;

/**
 * 실제 공고 주소 정답 케이스(area/geocode/cases.csv)로 판별기를 재요.
 *
 * <p>케이스는 2026-10 로컬에 모인 공고(LH 상세·마이홈·청년안심주택)와 매입임대·든든전세 주택목록에서 골랐고, 기대값은 도로명주소 검색 API와 주소
 * 사전(area.address_points)으로 확인했어요. 시군구 코드·주소관리번호 칸은 다음 단계(사전에서 찾기) 테스트가 써요.
 */
class AddressCasesTest {

  private static final double REQUIRED_ACCURACY = 0.95;

  @Test
  void parsesRealNoticeAddresses() throws Exception {
    List<Map<String, String>> cases = readCases();
    List<String> wrong = new ArrayList<>();
    for (Map<String, String> c : cases) {
      String why = mismatch(c, AddressParser.parse(c.get("address")));
      if (why != null) {
        wrong.add(c.get("address") + " → " + why);
      }
    }
    double accuracy = 1.0 - (double) wrong.size() / cases.size();

    assertThat(cases).hasSizeGreaterThanOrEqualTo(150);
    assertThat(accuracy)
        .as("정답률 %.1f%%, 틀린 것:%n%s", accuracy * 100, String.join("\n", wrong))
        .isGreaterThanOrEqualTo(REQUIRED_ACCURACY);
  }

  private static String mismatch(Map<String, String> c, ParsedAddress p) {
    Kind kind = Kind.valueOf(c.get("kind"));
    if (p.kind() != kind) {
      return "종류 " + p.kind() + " (기대 " + kind + ")";
    }
    if (!same(c.get("sido"), p.sido())) {
      return "시도 " + p.sido() + " (기대 " + c.get("sido") + ")";
    }
    if (!same(c.get("sigungu"), p.sigungu())) {
      return "시군구 " + p.sigungu() + " (기대 " + c.get("sigungu") + ")";
    }
    if (kind == Kind.ROAD) {
      String got =
          p.roadName()
              + "|"
              + (p.underground() ? 1 : 0)
              + "|"
              + p.buildingMain()
              + "|"
              + p.buildingSub();
      String expected =
          c.get("road_name")
              + "|"
              + c.get("underground")
              + "|"
              + c.get("bldg_main")
              + "|"
              + c.get("bldg_sub");
      return got.equals(expected) ? null : "도로명 " + got + " (기대 " + expected + ")";
    }
    if (kind == Kind.JIBUN) {
      String got =
          p.dong() + "|" + (p.mountain() ? 1 : 0) + "|" + p.jibunMain() + "|" + p.jibunSub();
      String expected =
          c.get("dong") + "|" + c.get("san") + "|" + c.get("jibun_main") + "|" + c.get("jibun_sub");
      return got.equals(expected) ? null : "지번 " + got + " (기대 " + expected + ")";
    }
    return null;
  }

  private static boolean same(String expected, String actual) {
    return (expected == null || expected.isEmpty()) ? actual == null : expected.equals(actual);
  }

  /** 따옴표로 감싼 칸(쉼표 포함)을 읽는 작은 CSV 읽기. */
  static List<Map<String, String>> readCases() throws Exception {
    try (InputStream in =
            AddressCasesTest.class.getClassLoader().getResourceAsStream("area/geocode/cases.csv");
        BufferedReader reader =
            new BufferedReader(new InputStreamReader(in, StandardCharsets.UTF_8))) {
      List<String> header = split(reader.readLine());
      List<Map<String, String>> rows = new ArrayList<>();
      String line;
      while ((line = reader.readLine()) != null) {
        if (line.isBlank()) {
          continue;
        }
        List<String> cells = split(line);
        java.util.LinkedHashMap<String, String> row = new java.util.LinkedHashMap<>();
        for (int i = 0; i < header.size(); i++) {
          row.put(header.get(i), i < cells.size() ? cells.get(i) : "");
        }
        rows.add(row);
      }
      return rows;
    }
  }

  private static List<String> split(String line) {
    List<String> cells = new ArrayList<>();
    StringBuilder cell = new StringBuilder();
    boolean quoted = false;
    for (int i = 0; i < line.length(); i++) {
      char ch = line.charAt(i);
      if (quoted) {
        if (ch == '"' && i + 1 < line.length() && line.charAt(i + 1) == '"') {
          cell.append('"');
          i++;
        } else if (ch == '"') {
          quoted = false;
        } else {
          cell.append(ch);
        }
      } else if (ch == '"') {
        quoted = true;
      } else if (ch == ',') {
        cells.add(cell.toString());
        cell.setLength(0);
      } else {
        cell.append(ch);
      }
    }
    cells.add(cell.toString());
    return cells;
  }
}
