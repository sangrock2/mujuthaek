package kr.mujuthaek.api.area.service;

import static org.assertj.core.api.Assertions.assertThat;

import kr.mujuthaek.api.area.domain.AddressMatch;
import kr.mujuthaek.api.area.domain.Coordinate;
import kr.mujuthaek.api.area.domain.GeocodeResult;
import kr.mujuthaek.api.area.domain.GeocodeResult.FailReason;
import org.junit.jupiter.api.Test;

class GeocodeSampleReportTest {

  private static GeocodeResult ok(String id) {
    return GeocodeResult.ok(
        new AddressMatch(id, "2611010100", "초량상로", 0, 1, 2, 35.1, 129.0, AddressMatch.Method.FILE),
        "26110");
  }

  @Test
  void showsSuccessRateMethodsCorrectnessAndFailures() {
    var report = new GeocodeSampleReport();
    report.add(new GeocodeSampleReport.Row("초량상로 1-2", "ROAD", "a", ok("a")));
    report.add(new GeocodeSampleReport.Row("다른로 3", "ROAD", "b", ok("c"))); // 정답과 다름
    report.add(
        new GeocodeSampleReport.Row(
            "모라동 656-6",
            "JIBUN",
            null,
            GeocodeResult.approx(new Coordinate(35.1, 129.0), "2653010200", "26530")
                .withRegionMismatch()));
    report.add(
        new GeocodeSampleReport.Row(
            "A17블록", "AREA_ONLY", null, GeocodeResult.failed(FailReason.NOT_FOUND, null)));

    String md = report.markdown();

    assertThat(md).contains("| 4 | 2 | 1 | 1 | 75.0% | 95.0% 못 넘음 |");
    assertThat(md).contains("| ROAD | OK FILE | 2 | 50.0% | 1 | 1 |");
    assertThat(md).contains("| JIBUN | APPROX CENTROID | 1 | 25.0% | 0 | 0 |");
    assertThat(md).contains("- NOT_FOUND 1");
    assertThat(md).contains("- OK FILE (정답과 다름): 다른로 3");
    assertThat(md).contains("- APPROX CENTROID (법정동 불일치): 모라동 656-6");
    assertThat(md).doesNotContain(": 초량상로 1-2"); // 정확히 맞은 줄은 목록에 없음
  }

  @Test
  void emptySampleHasNoFailureSection() {
    String md = new GeocodeSampleReport().markdown();

    assertThat(md).contains("| 0 | 0 | 0 | 0 | 0.0% |");
    assertThat(md).doesNotContain("실패 이유");
  }
}
