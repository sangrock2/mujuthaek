package kr.mujuthaek.api.common.region;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * 2026 행정구역 개편으로 폐지된 법정동코드 → 지금 코드 대응을 만들어요. 법정동코드표에는 예전 → 새 코드 칸이 없어서 계산해요.
 *
 * <p><b>이번 개편의 시군구 계보 안에서만</b> 이어요. 같은 시도 전체에서 동 이름으로 찾으면 동 이름이 겹치는 곳이 많아(같은 시도 안 2천여 개, 예: 서울 신사동은
 * 은평·강남에 있고 성동·서대문·서초 것은 폐지) 오래전에 폐지된 코드가 엉뚱한 곳으로 이어질 수 있어요.
 *
 * <ul>
 *   <li>시군구 계보: 인천 중구 28110 → 제물포구 28125·영종구 28155, 동구 28140 → 제물포구 28125, 서구 28260 → 서해구 28275·검단구
 *       28290, 화성시 41590 → 만세·효행·병점·동탄구 41591~41597, 부천시 41190~41199 → 원미·소사·오정구 41192·41194·41196
 *   <li>시도 통합: 광주 29·전남 46 → 전남광주 12, 강원 42 → 51, 전북 45 → 52 — 시군구 이름이 같은 것끼리
 *   <li>동·리: 위 계보의 새 시군구들 안에서 동 이름(시군구 뒤 글자)이 <b>하나만</b> 맞을 때만. 여러 개거나 없으면 대응 없음
 *   <li>계보 밖의 폐지 코드는 대응 없음
 * </ul>
 *
 * <p>시군구는 계보 그대로 여러 새 코드로 갈라질 수 있어요(28110 → 28125, 28155). 코드는 모두 10자리예요.
 */
final class RegionCodeChanges {

  /** 예전 시군구(5자리) → 새 시군구들. */
  static final Map<String, List<String>> SIGUNGU_LINEAGE = new LinkedHashMap<>();

  /** 통합된 예전 시도 → 새 시도 (시군구는 이름이 같은 것끼리). */
  static final Map<String, String> SIDO_MERGES =
      Map.of("29", "12", "46", "12", "42", "51", "45", "52");

  static {
    SIGUNGU_LINEAGE.put("28110", List.of("28125", "28155"));
    SIGUNGU_LINEAGE.put("28140", List.of("28125"));
    SIGUNGU_LINEAGE.put("28260", List.of("28275", "28290"));
    SIGUNGU_LINEAGE.put("41590", List.of("41591", "41593", "41595", "41597"));
    for (String bucheon : List.of("41190", "41191", "41193", "41195", "41197", "41199")) {
      SIGUNGU_LINEAGE.put(bucheon, List.of("41192", "41194", "41196"));
    }
  }

  /** 예전 코드 하나가 새 코드 하나로 가는 대응 (10자리). */
  record Change(String oldCode, String newCode) {}

  private RegionCodeChanges() {}

  static List<Change> compute(List<RegionCodeFile.Entry> entries) {
    Map<String, RegionCodeFile.Entry> byCode = new HashMap<>();
    for (RegionCodeFile.Entry e : entries) {
      byCode.put(e.code(), e);
    }
    Map<String, List<String>> lineage = lineage(entries, byCode);

    // 새 시군구 안의 지금 동·리: (시군구 5자리, 동 이름) → 코드들
    Map<String, List<String>> currentDongs = new HashMap<>();
    for (RegionCodeFile.Entry e : entries) {
      if (e.valid() && !e.code().endsWith("00000")) {
        currentDongs
            .computeIfAbsent(
                key(e.code().substring(0, 5), dongName(e, byCode)), k -> new ArrayList<>())
            .add(e.code());
      }
    }

    Set<Change> changes = new LinkedHashSet<>();
    for (Map.Entry<String, String> merge : SIDO_MERGES.entrySet()) {
      if (byCode.containsKey(merge.getKey() + "00000000")
          && !byCode.get(merge.getKey() + "00000000").valid()) {
        changes.add(new Change(merge.getKey() + "00000000", merge.getValue() + "00000000"));
      }
    }
    for (Map.Entry<String, List<String>> l : lineage.entrySet()) {
      RegionCodeFile.Entry old = byCode.get(l.getKey() + "00000");
      if (old == null || old.valid()) {
        continue; // 화성시·부천시처럼 시는 그대로 있고 아래 동만 일반구로 옮겨진 경우
      }
      for (String target : l.getValue()) {
        changes.add(new Change(l.getKey() + "00000", target + "00000"));
      }
    }
    for (RegionCodeFile.Entry e : entries) {
      String sigungu = e.code().substring(0, 5);
      if (e.valid() || e.code().endsWith("00000") || !lineage.containsKey(sigungu)) {
        continue;
      }
      String name = dongName(e, byCode);
      List<String> candidates = new ArrayList<>();
      for (String target : lineage.get(sigungu)) {
        candidates.addAll(currentDongs.getOrDefault(key(target, name), List.of()));
      }
      if (candidates.size() == 1) {
        changes.add(new Change(e.code(), candidates.get(0)));
      }
    }
    return List.copyOf(changes);
  }

  /**
   * 계보 표 + 통합된 시도의 폐지된 시군구(이름이 같은 지금 시군구). 계보 표는 예전 시군구가 지금도 있어도(화성시 41590) 그 아래 폐지된 동을 잇는 데 써요.
   */
  private static Map<String, List<String>> lineage(
      List<RegionCodeFile.Entry> entries, Map<String, RegionCodeFile.Entry> byCode) {
    Map<String, List<String>> lineage = new LinkedHashMap<>(SIGUNGU_LINEAGE);
    Map<String, String> currentSigungu = new HashMap<>(); // (시도, 시군구 이름) → 코드
    for (RegionCodeFile.Entry e : entries) {
      if (e.valid() && isSigungu(e.code())) {
        currentSigungu.put(
            key(e.code().substring(0, 2), sigunguName(e, byCode)), e.code().substring(0, 5));
      }
    }
    for (RegionCodeFile.Entry e : entries) {
      String newSido = SIDO_MERGES.get(e.code().substring(0, 2));
      if (newSido == null || e.valid() || !isSigungu(e.code())) {
        continue;
      }
      String target = currentSigungu.get(key(newSido, sigunguName(e, byCode)));
      if (target != null) {
        lineage.putIfAbsent(e.code().substring(0, 5), List.of(target));
      }
    }
    return lineage;
  }

  private static boolean isSigungu(String code) {
    return code.endsWith("00000") && !code.endsWith("00000000");
  }

  /** "광주광역시 동구" → "동구" (시도 이름 뒤). */
  private static String sigunguName(
      RegionCodeFile.Entry e, Map<String, RegionCodeFile.Entry> byCode) {
    RegionCodeFile.Entry sido = byCode.get(e.code().substring(0, 2) + "00000000");
    return after(e.fullName(), sido == null ? null : sido.fullName());
  }

  /** "인천광역시 중구 운서동" → "운서동" (시군구 이름 뒤). */
  private static String dongName(RegionCodeFile.Entry e, Map<String, RegionCodeFile.Entry> byCode) {
    RegionCodeFile.Entry sigungu = byCode.get(e.code().substring(0, 5) + "00000");
    return after(e.fullName(), sigungu == null ? null : sigungu.fullName());
  }

  private static String after(String fullName, String prefix) {
    if (prefix != null && fullName.startsWith(prefix + " ")) {
      return fullName.substring(prefix.length() + 1);
    }
    return fullName;
  }

  private static String key(String a, String b) {
    return a + "|" + b;
  }
}
