package kr.mujuthaek.api.common.region;

import java.io.BufferedReader;
import java.io.IOException;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 법정동코드표(법정동코드 · 법정동명 · 폐지여부)에서 시도·시군구만 골라요. 저장소 원본(쉼표 구분)과 행정표준코드관리시스템 받은 파일(탭 구분)을 둘 다 읽어요.
 *
 * <ul>
 *   <li>시도: 10자리 중 뒤 8자리가 0 (1100000000 서울특별시 → 11)
 *   <li>시군구: 뒤 5자리가 0이고 시군구 자리가 000이 아님 (1144000000 서울특별시 마포구 → 11440)
 *   <li>세종은 시도 줄(3600000000)이 없고 3611000000이 시도 겸 시군구라, 시도 36을 만들어 넣어요
 *   <li>읍면동·리는 쓰지 않아요
 * </ul>
 */
final class RegionCodeFile {

  /** 시도 짧은 이름 (화면 표시용). 이름 앞부분으로 찾아요. */
  private static final Map<String, String> SHORT_NAMES = new LinkedHashMap<>();

  static {
    SHORT_NAMES.put("전남광주", "전남광주"); // 2026 통합 (12). "전라남"·"광주"보다 먼저 봐요
    SHORT_NAMES.put("서울", "서울");
    SHORT_NAMES.put("부산", "부산");
    SHORT_NAMES.put("대구", "대구");
    SHORT_NAMES.put("인천", "인천");
    SHORT_NAMES.put("광주", "광주");
    SHORT_NAMES.put("대전", "대전");
    SHORT_NAMES.put("울산", "울산");
    SHORT_NAMES.put("세종", "세종");
    SHORT_NAMES.put("경기", "경기");
    SHORT_NAMES.put("강원", "강원");
    SHORT_NAMES.put("충청북", "충북");
    SHORT_NAMES.put("충청남", "충남");
    SHORT_NAMES.put("전라북", "전북");
    SHORT_NAMES.put("전북", "전북");
    SHORT_NAMES.put("전라남", "전남");
    SHORT_NAMES.put("경상북", "경북");
    SHORT_NAMES.put("경상남", "경남");
    SHORT_NAMES.put("제주", "제주");
  }

  /** 파일 한 줄에서 고른 시도·시군구. */
  record Row(
      String code,
      String level,
      String parentCode,
      String name,
      String fullName,
      String shortName,
      boolean valid) {}

  /** 파일 한 줄 그대로 (읍면동·리 포함). */
  record Entry(String code, String fullName, boolean valid) {}

  private RegionCodeFile() {}

  static List<Row> read(BufferedReader reader) throws IOException {
    return rows(entries(reader));
  }

  /** 모든 줄 (머리줄·빈 줄 빼고). 이름 끝 공백은 잘라요. */
  static List<Entry> entries(BufferedReader reader) throws IOException {
    List<Entry> entries = new ArrayList<>();
    String line;
    while ((line = reader.readLine()) != null) {
      String[] cells = line.split(line.indexOf('\t') >= 0 ? "\t" : ",");
      if (cells.length < 3 || !cells[0].trim().matches("[0-9]{10}")) {
        continue; // 머리줄·빈 줄
      }
      entries.add(new Entry(cells[0].trim(), cells[1].trim(), cells[2].trim().equals("존재")));
    }
    return entries;
  }

  static List<Row> rows(List<Entry> entries) {
    List<Row> rows = new ArrayList<>();
    Map<String, String> sidoNames = new LinkedHashMap<>();
    for (Entry entry : entries) {
      String code = entry.code();
      String fullName = entry.fullName();
      boolean valid = entry.valid();
      if (code.endsWith("00000000")) {
        String sido = code.substring(0, 2);
        sidoNames.put(sido, fullName);
        rows.add(new Row(sido, "SIDO", null, fullName, fullName, shortName(fullName), valid));
      } else if (code.endsWith("00000") && !code.startsWith("000", 2)) {
        String sido = code.substring(0, 2);
        if (!sidoNames.containsKey(sido) && !fullName.contains(" ")) {
          // 세종: 시도 줄 없이 시군구 줄 이름이 시도 이름이에요
          sidoNames.put(sido, fullName);
          rows.add(new Row(sido, "SIDO", null, fullName, fullName, shortName(fullName), valid));
        }
        String sidoName = sidoNames.getOrDefault(sido, "");
        String name =
            fullName.startsWith(sidoName + " ")
                ? fullName.substring(sidoName.length() + 1)
                : fullName; // 세종특별자치시처럼 시도와 이름이 같으면 그대로
        rows.add(new Row(code.substring(0, 5), "SIGUNGU", sido, name, fullName, null, valid));
      }
    }
    return rows;
  }

  static String shortName(String sidoName) {
    return SHORT_NAMES.entrySet().stream()
        .filter(e -> sidoName.startsWith(e.getKey()))
        .map(Map.Entry::getValue)
        .findFirst()
        .orElse(sidoName);
  }
}
