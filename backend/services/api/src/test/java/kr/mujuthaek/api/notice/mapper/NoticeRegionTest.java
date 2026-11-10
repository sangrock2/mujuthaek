package kr.mujuthaek.api.notice.mapper;

import static org.assertj.core.api.Assertions.assertThat;

import kr.mujuthaek.api.common.event.NoticeLocationsChanged;
import kr.mujuthaek.api.notice.domain.CompletedNotice;
import kr.mujuthaek.api.notice.dto.request.NoticeListFilter;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.node.ArrayNode;
import tools.jackson.databind.node.ObjectNode;

/** 지역 코드 5자리 규칙(2026-10-20 결정): 서비스는 앞 5자리만 쓰고, 시군구 자리 000은 시도 단위예요. */
class NoticeRegionTest {

  private static ObjectNode example() {
    return (ObjectNode)
        NoticeContractTest.resource("/contracts/examples/extraction.completed.json").deepCopy();
  }

  private static ObjectNode detail(ObjectNode envelope) {
    return (ObjectNode) envelope.path("payload").path("notice");
  }

  private static ExtractionEvent withLocations(String regionCode, String... codes) {
    ObjectNode envelope = example();
    ArrayNode locations = (ArrayNode) detail(envelope).path("locations");
    ObjectNode first = (ObjectNode) locations.get(0);
    locations.removeAll();
    for (int i = 0; i < codes.length; i++) {
      ObjectNode location = first.deepCopy();
      if (i > 0) {
        location.put("id", "location-" + i); // 첫 위치 ID는 다른 항목이 가리키므로 그대로
      }
      location.put("regionCode", codes[i]);
      locations.add(location);
    }
    ((ObjectNode) envelope.path("payload")).put("regionCode", regionCode);
    return ExtractionEvent.from(envelope);
  }

  @Test
  void 시도까지만_아는_위치는_시도_단위로_색인해_시도_검색에_나온다() {
    ExtractionEvent event = withLocations("11000", "1100000000");

    assertThat(NoticeContent.sigunguCodes(event)).containsExactly("11000");
  }

  @Test
  void 같은_시도의_여러_시군구는_시군구마다_색인하고_이벤트_코드는_시도_단위다() {
    ExtractionEvent event = withLocations("11000", "1111000000", "1114000000");

    assertThat(NoticeContent.sigunguCodes(event)).containsExactly("11110", "11140");
    assertThat(NoticeProjection.regionCode(event.notice())).isEqualTo("11000");
  }

  @Test
  void 여러_시도에_걸치면_이벤트_코드는_없다() {
    ExtractionEvent event = withLocations(null, "1111000000", "4111000000");

    assertThat(NoticeProjection.regionCode(event.notice())).isNull();
    assertThat(NoticeContent.sigunguCodes(event)).containsExactly("11110", "41110");
  }

  @Test
  void 시도_단위_5자리로_검색하면_그_시도_전체를_찾는다() {
    // 11000(서울특별시)으로 검색하면 11로 시작하는 모든 코드(서울 단위 공고 + 서울 안 모든 구 공고)
    assertThat(search("11000").sidoCodes()).containsExactly("11");
    assertThat(search("11000").sigunguCodes()).isEmpty();
    assertThat(search("11").sidoCodes()).containsExactly("11");
    assertThat(search("11680").sigunguCodes()).containsExactly("11680"); // 구 검색에는 시도 단위 공고가 나오지 않음
    assertThat(search("11680").sidoCodes()).isEmpty();
  }

  @Test
  void 보류한_공고일과_공급_유형은_쓰지_않는다() {
    ObjectNode envelope = example();
    ObjectNode payload = (ObjectNode) envelope.path("payload");
    ObjectNode quality = (ObjectNode) detail(envelope).path("quality");
    ArrayNode held = payload.putArray("heldItems");
    for (String target : new String[] {"/notice/announcedOn", "/notice/supplyType"}) {
      ObjectNode item = held.addObject();
      item.put("target", target);
      item.put("extent", "ITEM");
      item.putArray("codes").add("API_MISMATCH");
      item.put("description", "확인이 필요합니다.");
    }
    quality.set("heldItems", held.deepCopy());
    ArrayNode issues = quality.putArray("reviewIssues");
    for (String target : new String[] {"/notice/announcedOn", "/notice/supplyType"}) {
      ObjectNode issue = issues.addObject();
      issue.put("code", "API_MISMATCH");
      issue.put("target", target);
      issue.put("description", "확인이 필요합니다.");
    }
    ((ObjectNode) quality.path("verification")).put("status", "PARTIALLY_PASSED");
    payload.put("reviewStatus", "PARTIALLY_PASSED");

    CompletedNotice listValues = CompletedNotice.from(ExtractionEvent.from(envelope).payload());

    assertThat(listValues.supplyTypeText()).isNull(); // 목록·필터에 보류한 값을 쓰지 않음
    assertThat(listValues.noticeType()).isNull();
    assertThat(listValues.title()).isNotNull();
  }

  @Test
  void 원문_위치에_전국이_명시된_공고만_전국_대상이다() {
    assertThat(NoticeContent.nationwide(withRegionText("전국"))).isTrue();
    assertThat(NoticeContent.nationwide(withRegionText("전국 단위"))).isTrue();
    assertThat(NoticeContent.nationwide(withRegionText("전국(수도권 포함)"))).isTrue();
    assertThat(NoticeContent.nationwide(withRegionText("대구경북지역"))).isFalse();
    assertThat(NoticeContent.nationwide(withRegionText("전국가"))).isFalse(); // 「전국」으로 시작만 하는 다른 낱말
    assertThat(NoticeContent.nationwide(withLocations("11650", "1165000000"))).isFalse();
  }

  @Test
  void 신청_자격이_전국이어도_특정_단지가_있으면_그_지역_공고다() {
    // 실측 LH 양산시 매각 공고: 「전국(국내)에 거주하는 … 에게 공급」이지만 주택은 양산시 단지
    ObjectNode envelope = example();
    ArrayNode locations = (ArrayNode) detail(envelope).path("locations");
    ObjectNode said = ((ObjectNode) locations.get(0)).deepCopy();
    said.put("id", "location-nationwide");
    said.put("region", "전국");
    locations.add(said);
    withoutCode(envelope, locations.size() - 1);

    assertThat(NoticeContent.nationwide(ExtractionEvent.from(envelope))).isFalse();
  }

  @Test
  void 대상_지역_AREA는_전체_색인이고_주택_위치로_보내지_않는다() {
    // 「대구경북지역 … 예비입주자 모집공고」: 단지가 없어 대상 지역을 대구·경북 AREA로 적음
    ObjectNode envelope = example();
    ArrayNode locations = (ArrayNode) detail(envelope).path("locations");
    ObjectNode first = (ObjectNode) locations.get(0);
    first.put("kind", "AREA").put("region", "대구").put("regionCode", "2700000000");
    ObjectNode second = first.deepCopy();
    second.put("id", "area-gyeongbuk").put("region", "경북").put("regionCode", "4700000000");
    locations.add(second);
    ((ObjectNode) envelope.path("payload")).putNull("regionCode"); // 여러 시도라 이벤트 코드 없음

    ExtractionEvent event = ExtractionEvent.from(envelope);

    assertThat(NoticeContent.regions(event))
        .containsExactlyInAnyOrderEntriesOf(java.util.Map.of("27000", true, "47000", true));
    assertThat(NoticeContent.locations(event)).isEmpty(); // 지역 점수 계산 대상 아님
    assertThat(NoticeContent.nationwide(event)).isFalse();
  }

  /** 보류 항목을 붙인 이벤트 (계약 검사를 거치지 않고 값만 바꿔요). */
  private static ExtractionEvent withHeld(ExtractionEvent event, String... targets) {
    ArrayNode held = tools.jackson.databind.node.JsonNodeFactory.instance.arrayNode();
    for (String target : targets) {
      held.addObject().put("target", target).putArray("codes").add("API_VALUE_MISMATCH");
    }
    return new ExtractionEvent(
        event.eventId(),
        event.rawPostId(),
        event.rawVersion(),
        event.field(),
        event.title(),
        event.reviewStatus(),
        event.reprocess(),
        event.regionCode(),
        event.applyStartOn(),
        event.applyEndOn(),
        event.notice(),
        event.conditions(),
        held,
        event.applicationWindows(),
        event.payload());
  }

  @Test
  void 보류한_위치의_지역_코드는_색인과_area_입력에_쓰지_않는다() {
    ExtractionEvent event = withLocations("11000", "1111000000", "1114000000");

    ExtractionEvent codeHeld = withHeld(event, "/locations/1/regionCode");
    assertThat(NoticeContent.sigunguCodes(codeHeld)).containsExactly("11110");
    assertThat(NoticeContent.regions(codeHeld)).containsOnlyKeys("11110");
    assertThat(NoticeContent.locations(codeHeld))
        .extracting(NoticeLocationsChanged.Location::regionCode)
        .containsExactly("1111000000", null); // 위치는 보내되 미확정 코드는 빼요

    ExtractionEvent locationHeld = withHeld(event, "/locations/1");
    assertThat(NoticeContent.sigunguCodes(locationHeld)).containsExactly("11110");
    assertThat(NoticeContent.locations(locationHeld)).hasSize(1);
  }

  @Test
  void 이벤트_지역_코드는_보류한_위치_지역을_코드_없는_위치로_본다() {
    ObjectNode notice = detail(example());
    ArrayNode locations = (ArrayNode) notice.path("locations");
    ObjectNode second = ((ObjectNode) locations.get(0)).deepCopy();
    second.put("id", "location-2").put("regionCode", "1114000000");
    ((ObjectNode) locations.get(0)).put("regionCode", "1111000000");
    locations.add(second);
    assertThat(NoticeProjection.regionCode(notice)).isEqualTo("11000");

    ((ObjectNode) notice.path("quality"))
        .putArray("heldItems")
        .addObject()
        .put("target", "/locations/1/regionCode")
        .putArray("codes")
        .add("API_VALUE_MISMATCH");
    assertThat(NoticeProjection.regionCode(notice)).isNull();
  }

  @Test
  void 지역을_보류한_위치가_있으면_전국으로_보지_않는다() {
    ExtractionEvent said = withRegionText("전국");

    assertThat(NoticeContent.nationwide(said)).isTrue();
    assertThat(NoticeContent.nationwide(withHeld(said, "/locations/0/region"))).isFalse();
  }

  @Test
  void 대표_지역은_한_시군구면_그_코드_한_시도면_시도_코드_여러_시도면_null이다() {
    assertThat(NoticeContent.representativeRegion(java.util.List.of("11650"))).isEqualTo("11650");
    assertThat(NoticeContent.representativeRegion(java.util.List.of("11650", "11680")))
        .isEqualTo("11000");
    assertThat(NoticeContent.representativeRegion(java.util.List.of("27000", "47000"))).isNull();
    assertThat(NoticeContent.representativeRegion(java.util.List.of())).isNull();
  }

  @Test
  void 주택_위치의_시도_단위_코드는_전체_색인이_아니다() {
    ExtractionEvent event = withLocations("11000", "1100000000");

    assertThat(NoticeContent.regions(event)).containsExactly(java.util.Map.entry("11000", false));
  }

  private static ExtractionEvent withRegionText(String region) {
    ObjectNode envelope = example();
    ((ObjectNode) detail(envelope).path("locations").get(0)).put("region", region);
    if (region.startsWith("전국")) {
      withoutCode(envelope, 0); // 추출은 「전국」을 지역 코드로 바꾸지 못해 null로 둠
    }
    return ExtractionEvent.from(envelope);
  }

  /** 위치 index의 지역 코드를 비우고, 계약대로 이벤트 지역 코드도 null·누락 사유를 남겨요. */
  private static void withoutCode(ObjectNode envelope, int index) {
    ((ObjectNode) detail(envelope).path("locations").get(index)).putNull("regionCode");
    ((ObjectNode) envelope.path("payload")).putNull("regionCode");
    ObjectNode missing =
        ((ArrayNode) detail(envelope).path("quality").path("missingFields")).addObject();
    missing.put("target", "/locations/" + index + "/regionCode");
    missing.put("reason", "NOT_APPLICABLE");
    missing.put("description", "지역 코드로 정할 수 없습니다.");
  }

  private static NoticeListFilter search(String region) {
    return new NoticeListFilter(null, java.util.List.of(region), null, null, null, null, null);
  }
}
