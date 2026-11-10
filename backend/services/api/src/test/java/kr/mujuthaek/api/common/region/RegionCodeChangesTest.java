package kr.mujuthaek.api.common.region;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.BufferedReader;
import java.io.StringReader;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;

/** 빌드에 들어간 실제 법정동코드표(2026-09-29)로 예전 → 지금 코드 대응을 확인해요. */
class RegionCodeChangesTest {

  private static Map<String, List<String>> changes;

  @BeforeAll
  static void compute() throws Exception {
    String text = RegionLoader.bundled().text();
    List<RegionCodeFile.Entry> entries =
        RegionCodeFile.entries(new BufferedReader(new StringReader(text)));
    changes =
        RegionCodeChanges.compute(entries).stream()
            .collect(
                Collectors.groupingBy(
                    RegionCodeChanges.Change::oldCode,
                    Collectors.mapping(RegionCodeChanges.Change::newCode, Collectors.toList())));
  }

  @Test
  void dongsFollowTheirNewSigunguWhenTheNameMatchesOnce() {
    assertThat(changes.get("2811014700")).containsExactly("2815510300"); // 중구 운서동 → 영종구 운서동
    assertThat(changes.get("2811012400")).containsExactly("2812513100"); // 중구 신포동 → 제물포구 신포동
    // 화성시·부천시는 시가 그대로 있고 아래 동만 일반구로
    assertThat(changes.get("4159011700")).containsExactly("4159510200"); // 병점동 → 병점구 병점동
    assertThat(changes.get("4159025325")).containsExactly("4159325025"); // 봉담읍 와우리 → 효행구 봉담읍 와우리
    assertThat(changes.get("4119000100")).containsExactly("4119210200"); // 심곡동 → 원미구 심곡동
  }

  @Test
  void codesOutsideThisReformHaveNoChange() {
    // 서울 서초구 신사동(폐지)은 같은 시도에 같은 이름이 있어도(강남·은평 신사동) 이번 개편 계보 밖이라 대응 없음
    assertThat(changes).doesNotContainKey("1165011300");
  }

  @Test
  void sigunguMaySplitIntoSeveral() {
    assertThat(changes.get("2811000000")).containsExactlyInAnyOrder("2812500000", "2815500000");
    assertThat(changes.get("2814000000")).containsExactly("2812500000");
    assertThat(changes.get("2826000000")).containsExactlyInAnyOrder("2827500000", "2829000000");
    assertThat(changes).doesNotContainKey("4159000000"); // 화성시는 지금도 있음
  }

  @Test
  void mergedSidosFollowBySigunguName() {
    assertThat(changes.get("2900000000")).containsExactly("1200000000"); // 광주 → 전남광주
    assertThat(changes.get("4600000000")).containsExactly("1200000000"); // 전남 → 전남광주
    assertThat(changes.get("2911000000")).containsExactly("1221000000"); // 광주 동구 → 전남광주 동구
    assertThat(changes.get("4211000000")).containsExactly("5111000000"); // 강원도 춘천시 → 강원특별자치도 춘천시
  }

  @Test
  void eachDongGoesToOneCodeOnly() {
    assertThat(changes.entrySet())
        .filteredOn(e -> !e.getKey().endsWith("00000"))
        .allSatisfy(e -> assertThat(e.getValue()).hasSize(1));
  }
}
