package kr.mujuthaek.api.notice.controller;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.jayway.jsonpath.JsonPath;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import kr.mujuthaek.api.common.pagination.CursorCodec;
import kr.mujuthaek.api.common.pagination.CursorKey;
import kr.mujuthaek.api.notice.NoticeApiFixture;
import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.MockMvc;
import tools.jackson.databind.node.ArrayNode;
import tools.jackson.databind.node.ObjectNode;

class NoticeUnitsApiTest {

  private final NoticeApiFixture f = new NoticeApiFixture();
  private final MockMvc mvc = f.mvc(new NoticeController(f.queries));

  /** 예시의 201호를 202호·203호로 늘린 공고 (203호는 다른 건물). ID·참조는 계약에 맞게 새로 써요. */
  private UUID threeUnits() {
    return threeUnits("203");
  }

  /** otherBuilding 호만 B동이에요. */
  private UUID threeUnits(String otherBuilding) {
    return f.notice(
        p -> {
          ObjectNode detail = (ObjectNode) p.get("notice");
          ArrayNode locations = (ArrayNode) detail.get("locations");
          ObjectNode buildingB = ((ObjectNode) locations.get(0)).deepCopy();
          buildingB.put("id", "building-b").put("buildingName", "가상건물 B동");
          buildingB.put("address", "서울특별시 종로구 가상로 2");
          locations.add(buildingB);
          ArrayNode groups = (ArrayNode) detail.get("supplyGroups");
          ObjectNode first = (ObjectNode) groups.get(0);
          for (String unit : List.of("202", "203")) {
            String id = "unit-" + unit;
            String location = unit.equals(otherBuilding) ? "building-b" : "building-a";
            ObjectNode copy = first.deepCopy();
            copy.put("id", id);
            copy.put("unitLabel", unit + "호");
            copy.put("locationId", location);
            scope((ObjectNode) copy.get("scope"), location, id);
            for (var price : copy.get("prices")) {
              ((ObjectNode) price).put("id", price.get("id").asString() + "-" + unit);
              scope((ObjectNode) price.get("scope"), location, id);
            }
            groups.add(copy);
          }
        });
  }

  private static void scope(ObjectNode scope, String location, String group) {
    scope.putArray("locationIds").add(location);
    scope.putArray("supplyGroupIds").add(group);
  }

  @Test
  void listsUnitsWithAddressAndPrices() throws Exception {
    UUID id = threeUnits();

    mvc.perform(get("/api/v1/notices/{id}/units", id))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.items.length()").value(3))
        .andExpect(jsonPath("$.items[0].unitLabel").value("201호"))
        .andExpect(jsonPath("$.items[0].siteId").value("building-a"))
        .andExpect(jsonPath("$.items[0].address").value("서울특별시 종로구 가상로 1"))
        .andExpect(jsonPath("$.items[0].floor").value("2층"))
        .andExpect(jsonPath("$.items[0].houseType").value("20A"))
        .andExpect(jsonPath("$.items[0].depositWon").value(1000000))
        .andExpect(jsonPath("$.items[0].rentWon").value(100000))
        .andExpect(jsonPath("$.items[0].prices.length()").value(1))
        .andExpect(jsonPath("$.items[0].prices[0].depositWon").value(1000000))
        .andExpect(jsonPath("$.items[0].prices[0].rentWon").value(100000));
  }

  @Test
  void groupsUnitsBySiteAndNamesTheSite() throws Exception {
    UUID id = threeUnits("202"); // 원문 순서는 A동 201 · B동 202 · A동 203

    var body =
        mvc.perform(get("/api/v1/notices/{id}/units", id))
            .andExpect(status().isOk())
            .andReturn()
            .getResponse()
            .getContentAsString();

    List<String> sites = JsonPath.read(body, "$.items[*].siteId");
    assertThat(sites).containsExactly("building-a", "building-a", "building-b");
    assertThat(JsonPath.<List<String>>read(body, "$.items[*].unitLabel"))
        .containsExactly("201호", "203호", "202호");
    List<String> names = JsonPath.read(body, "$.items[*].siteName");
    assertThat(names.get(2)).isEqualTo("가상건물 B동");
  }

  @Test
  void pagesAndFiltersBySite() throws Exception {
    UUID id = threeUnits();

    List<String> labels = new ArrayList<>();
    String cursor = null;
    do {
      var request = get("/api/v1/notices/{id}/units", id).param("size", "2");
      if (cursor != null) {
        request.param("cursor", cursor);
      }
      String body = mvc.perform(request).andReturn().getResponse().getContentAsString();
      labels.addAll(JsonPath.read(body, "$.items[*].unitLabel"));
      cursor = JsonPath.read(body, "$.nextCursor");
    } while (cursor != null);
    assertThat(labels).containsExactly("201호", "202호", "203호");

    mvc.perform(get("/api/v1/notices/{id}/units", id).param("siteId", "building-b"))
        .andExpect(jsonPath("$.items.length()").value(1))
        .andExpect(jsonPath("$.items[0].unitLabel").value("203호"));
  }

  @Test
  void craftedPositionCursorIs400Not500() throws Exception {
    UUID id = threeUnits();

    // 커서는 Base64라 위치 값을 바꿔 보낼 수 있어요. 음수나 아주 큰 값이면 목록 범위를 벗어나 500이 났어요
    for (String position : List.of("-5", String.valueOf(Integer.MAX_VALUE), "abc")) {
      String cursor = CursorCodec.encode(new CursorKey("UNITS", position, id));
      mvc.perform(get("/api/v1/notices/{id}/units", id).param("cursor", cursor))
          .andExpect(status().isBadRequest())
          .andExpect(jsonPath("$.code").value("INVALID_CURSOR"));
    }
  }

  @Test
  void noticesWithoutUnitsGiveAnEmptyList() throws Exception {
    UUID id =
        f.notice(
            p -> {
              ObjectNode detail = (ObjectNode) p.get("notice");
              detail.putArray("supplyGroups");
              ((ObjectNode) detail.get("quality").get("coverage").get("supplyGroups"))
                  .put("status", "NOT_IN_SOURCE")
                  .put("reason", "원문에 공급 묶음이 없어요");
            });

    mvc.perform(get("/api/v1/notices/{id}/units", id))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.items.length()").value(0))
        .andExpect(jsonPath("$.hasNext").value(false));
  }

  @Test
  void tamperedCursorIsInvalid() throws Exception {
    UUID id = threeUnits();
    String bad = CursorCodec.encode(new CursorKey("UNITS", "많이", id));

    mvc.perform(get("/api/v1/notices/{id}/units", id).param("cursor", bad))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("INVALID_CURSOR"));
    mvc.perform(get("/api/v1/notices/{id}/units", UUID.randomUUID()))
        .andExpect(status().isNotFound());
  }
}
