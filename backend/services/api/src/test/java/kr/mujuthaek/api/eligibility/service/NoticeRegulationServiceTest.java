package kr.mujuthaek.api.eligibility.service;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.UUID;
import kr.mujuthaek.api.eligibility.dto.response.NoticeRegulationResponse.Area;
import kr.mujuthaek.api.eligibility.repository.CriteriaAdminStore.RegulatedArea;
import org.junit.jupiter.api.Test;

/** 공고 지역과 규제지역 맞추기, 안내 문장. */
class NoticeRegulationServiceTest {

  private static RegulatedArea area(String region, String kind) {
    return new RegulatedArea(
        UUID.randomUUID(),
        region,
        kind,
        null,
        LocalDate.of(2026, 1, 1),
        null,
        "국토교통부 공고",
        "admin-1",
        OffsetDateTime.now());
  }

  @Test
  void sameDistrictOrWholeCityMatches() {
    var active =
        List.of(
            area("11680", "SPECULATION_OVERHEATED"),
            area("41000", "ADJUSTMENT_TARGET"),
            area("26110", "SPECULATION"));
    var gangnam = NoticeRegulationService.match(List.of("1168000000"), active);
    assertThat(gangnam).extracting(Area::kindLabel).containsExactly("투기과열지구");
    assertThat(gangnam.get(0).partial()).isFalse();
    var suwon = NoticeRegulationService.match(List.of("4111100000"), active);
    assertThat(suwon).extracting(Area::kind).containsExactly("ADJUSTMENT_TARGET");
    assertThat(NoticeRegulationService.match(List.of("2711000000"), active)).isEmpty();
  }

  @Test
  void citiesWithGeneralDistrictsMatchTheirDistricts() {
    // 수원시(41110)를 지정하면 장안구(41111) 공고도 걸려요
    var city = List.of(area("41110", "ADJUSTMENT_TARGET"));
    assertThat(NoticeRegulationService.match(List.of("4111100000"), city))
        .singleElement()
        .extracting(Area::partial)
        .isEqualTo(false);
    // 영통구(41117)만 지정됐으면 수원시 전체 공고는 일부만 걸려요(partial)
    var district = List.of(area("41117", "SPECULATION_OVERHEATED"));
    assertThat(NoticeRegulationService.match(List.of("4111000000"), district))
        .singleElement()
        .extracting(Area::partial)
        .isEqualTo(true);
    // 다른 구(권선구 41113)는 걸리지 않아요
    assertThat(NoticeRegulationService.match(List.of("4111300000"), district)).isEmpty();
    // 2026-11-10 재검토: 끝자리 0 모양으로 시를 정해 영동군(43740) 규제지역에 증평군(43745) 공고가 걸렸음
    assertThat(
            NoticeRegulationService.match(
                List.of("4374500000"), List.of(area("43740", "SPECULATION"))))
        .isEmpty();
    assertThat(
            NoticeRegulationService.match(
                List.of("4374000000"), List.of(area("43745", "SPECULATION"))))
        .isEmpty();
    // 시 단위 코드끼리는 앞 4자리가 달라 섞이지 않아요(남양주 41360 · 오산 41370)
    assertThat(
            NoticeRegulationService.match(
                List.of("4136000000"), List.of(area("41370", "SPECULATION"))))
        .isEmpty();
  }

  @Test
  void nationwideNoticeIsNotRegulatedAndCityWideNoticeIsPartial() {
    var active = List.of(area("11680", "SPECULATION_OVERHEATED"));
    assertThat(NoticeRegulationService.match(List.of(), active)).isEmpty();
    var seoul = NoticeRegulationService.match(List.of("1100000000"), active);
    assertThat(seoul).singleElement().extracting(Area::partial).isEqualTo(true);
    assertThat(NoticeRegulationService.guidance(seoul))
        .hasSize(2)
        .last()
        .asString()
        .contains("일부 시군구만");
  }

  @Test
  void guidanceIsOnePerKindInAFixedOrder() {
    var areas =
        NoticeRegulationService.match(
            List.of("1168000000", "1165000000"),
            List.of(
                area("11650", "SPECULATION"),
                area("11680", "SPECULATION_OVERHEATED"),
                area("11650", "SPECULATION_OVERHEATED")));
    var guidance = NoticeRegulationService.guidance(areas);
    assertThat(guidance).hasSize(2);
    assertThat(guidance.get(0)).startsWith("투기과열지구예요").contains("공고문을 확인하세요");
    assertThat(guidance.get(1)).startsWith("투기지역이에요");
  }
}
