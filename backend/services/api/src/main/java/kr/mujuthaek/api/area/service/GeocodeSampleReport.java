package kr.mujuthaek.api.area.service;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.TreeMap;
import kr.mujuthaek.api.area.domain.GeocodeResult;
import kr.mujuthaek.api.area.domain.GeocodeResult.Status;

/**
 * 주소 샘플을 돌린 결과 보고서 (계획 17번): 성공률(OK+APPROX, 목표 95%), 방법별 비율, 실패 이유 상위, 정답 주소 ID가 있으면 맞음·다름. 마크다운이라
 * .docs에 그대로 붙여요.
 */
public final class GeocodeSampleReport {

  static final double TARGET = 0.95;

  /** 샘플 한 줄 결과. expectedAddressId는 정답 주소 ID (모르면 null). */
  public record Row(String address, String kind, String expectedAddressId, GeocodeResult result) {}

  private final List<Row> rows = new ArrayList<>();

  public void add(Row row) {
    rows.add(row);
  }

  public String markdown() {
    int total = rows.size();
    long ok = count(Status.OK);
    long approx = count(Status.APPROX);
    long failed = count(Status.FAILED);
    double success = total == 0 ? 0 : (ok + approx) / (double) total;

    StringBuilder out = new StringBuilder();
    out.append("| 전체 | OK | APPROX | FAILED | 성공률(OK+APPROX) | 목표 |\n");
    out.append("| --- | --- | --- | --- | --- | --- |\n");
    out.append(
        String.format(
            Locale.ROOT,
            "| %d | %d | %d | %d | %s | %s %s |%n",
            total,
            ok,
            approx,
            failed,
            percent(success),
            percent(TARGET),
            success >= TARGET ? "넘음" : "못 넘음"));

    out.append("\n| 종류 | 결과 | 수 | 비율 | 정답 맞음 | 정답 다름 |\n| --- | --- | --- | --- | --- | --- |\n");
    Map<String, List<Row>> byWay = new TreeMap<>();
    for (Row r : rows) {
      byWay.computeIfAbsent(r.kind() + " | " + way(r.result()), k -> new ArrayList<>()).add(r);
    }
    byWay.forEach(
        (way, list) ->
            out.append(
                String.format(
                    Locale.ROOT,
                    "| %s | %d | %s | %d | %d |%n",
                    way,
                    list.size(),
                    percent(list.size() / (double) total),
                    list.stream().filter(GeocodeSampleReport::correct).count(),
                    list.stream().filter(GeocodeSampleReport::wrong).count())));

    Map<String, Long> reasons = new LinkedHashMap<>();
    rows.stream()
        .filter(r -> r.result().status() == Status.FAILED)
        .map(r -> r.result().failReason().name())
        .forEach(reason -> reasons.merge(reason, 1L, Long::sum));
    if (!reasons.isEmpty()) {
      out.append("\n실패 이유 상위\n\n");
      reasons.entrySet().stream()
          .sorted(Map.Entry.<String, Long>comparingByValue(Comparator.reverseOrder()))
          .limit(5)
          .forEach(
              e ->
                  out.append("- ")
                      .append(e.getKey())
                      .append(' ')
                      .append(e.getValue())
                      .append('\n'));
    }
    List<Row> notExact =
        rows.stream().filter(r -> r.result().status() != Status.OK || wrong(r)).toList();
    if (!notExact.isEmpty()) {
      out.append("\n정확한 좌표가 아닌 줄\n\n");
      notExact.forEach(
          r ->
              out.append("- ")
                  .append(way(r.result()))
                  .append(wrong(r) ? " (정답과 다름)" : "")
                  .append(r.result().regionMismatch() ? " (법정동 불일치)" : "")
                  .append(": ")
                  .append(r.address())
                  .append('\n'));
    }
    return out.toString();
  }

  private long count(Status status) {
    return rows.stream().filter(r -> r.result().status() == status).count();
  }

  private static String way(GeocodeResult r) {
    return r.status() + " " + (r.method() != null ? r.method() : r.failReason());
  }

  private static boolean correct(Row r) {
    return r.expectedAddressId() != null
        && r.result().addressId() != null
        && r.expectedAddressId().equals(r.result().addressId());
  }

  private static boolean wrong(Row r) {
    return r.expectedAddressId() != null
        && r.result().addressId() != null
        && !r.expectedAddressId().equals(r.result().addressId());
  }

  private static String percent(double v) {
    return String.format(Locale.ROOT, "%.1f%%", v * 100);
  }
}
