package kr.mujuthaek.api.notice.mapper;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatCode;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.io.IOException;
import java.io.InputStream;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.stream.Stream;
import org.junit.jupiter.api.DynamicTest;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestFactory;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;
import tools.jackson.databind.node.ArrayNode;
import tools.jackson.databind.node.ObjectNode;

class NoticeContractTest {
  private static final JsonMapper JSON = JsonMapper.builder().build();

  static JsonNode resource(String name) {
    try (InputStream input = NoticeContractTest.class.getResourceAsStream(name)) {
      return JSON.readTree(input);
    } catch (IOException e) {
      throw new IllegalStateException(e);
    }
  }

  @TestFactory
  Stream<DynamicTest> 파이썬과_같은_계약_경계_사례() {
    JsonNode cases = resource("/contracts/tests/fixtures/extraction-boundaries.json");
    List<DynamicTest> tests = new ArrayList<>();
    for (JsonNode c : cases.path("cases")) {
      tests.add(
          DynamicTest.dynamicTest(
              c.path("name").asString(),
              () -> {
                JsonNode event = resource("/contracts/examples/" + cases.path("base").asString());
                for (JsonNode operation : c.path("operations")) {
                  String path = operation.path("path").asString();
                  int last = path.lastIndexOf('/');
                  JsonNode parent = event.at(path.substring(0, last));
                  String key = path.substring(last + 1).replace("~1", "/").replace("~0", "~");
                  if (parent.isArray()) {
                    if (operation.path("remove").asBoolean(false))
                      ((ArrayNode) parent).remove(Integer.parseInt(key));
                    else ((ArrayNode) parent).set(Integer.parseInt(key), operation.path("value"));
                  } else if (operation.path("remove").asBoolean(false))
                    ((ObjectNode) parent).remove(key);
                  else ((ObjectNode) parent).set(key, operation.path("value"));
                }
                if (c.path("valid").asBoolean())
                  assertThatCode(() -> ExtractionEvent.from(event)).doesNotThrowAnyException();
                else
                  assertThatThrownBy(() -> ExtractionEvent.from(event))
                      .isInstanceOf(ExtractionEvent.InvalidEventException.class)
                      .hasMessageStartingWith(c.path("errorCode").asString())
                      .hasMessageNotContaining("review-placeholder-not-a-real-key");
              }));
    }
    return tests.stream();
  }

  @Test
  void 실제_추출_결과도_같은_계약을_통과한다() {
    ExtractionEvent event =
        ExtractionEvent.from(resource("/notice/extraction-completed-seoripul.json"));
    assertThat(event.conditions()).allSatisfy(c -> assertThat(c.path("scope").isObject()).isTrue());
    assertThat(event.applicationWindows()).isNotEmpty();
    ExtractionEvent stored = ExtractionEvent.fromStored(event.eventId(), event.payload());
    assertThat(stored.conditions()).isEqualTo(event.conditions());
  }

  @Test
  void 글자_범위_근거의_쪽_번호는_선택이고_쪽_수_안이어야_한다() {
    // 추출이 PDF 글자 근거의 글자 범위에 쪽 번호(page·printedPage)를 함께 실어요(요구 2-07)
    JsonNode event = resource("/notice/extraction-completed-seoripul.json");
    JsonNode notice = event.path("payload").path("notice");
    ObjectNode locator = (ObjectNode) notice.path("evidence").get(0).path("locator");
    assertThat(locator.path("kind").asString()).isEqualTo("TEXT_RANGE");
    locator.put("page", 4).put("printedPage", "- 3 -");
    assertThatCode(() -> ExtractionEvent.from(event)).doesNotThrowAnyException();
    locator.putNull("printedPage");
    assertThatCode(() -> ExtractionEvent.from(event)).doesNotThrowAnyException();

    for (JsonNode d : notice.path("documents"))
      if (d.path("id").asString().equals("pdf-text")) ((ObjectNode) d).put("pageCount", 3);
    assertThatThrownBy(() -> ExtractionEvent.from(event))
        .isInstanceOf(ExtractionEvent.InvalidEventException.class)
        .hasMessageStartingWith("PAGE_OUT_OF_RANGE");

    locator.put("page", 0);
    assertThatThrownBy(() -> ExtractionEvent.from(event))
        .isInstanceOf(ExtractionEvent.InvalidEventException.class);
  }

  @Test
  void 하위_필드를_보류한_상시_모집은_재계산에서도_제외한다() {
    ObjectNode detail =
        (ObjectNode)
            resource("/contracts/examples/extraction.completed.json")
                .path("payload")
                .path("notice");
    JsonNode schedules = detail.path("schedules");
    for (int i = 0; i < schedules.size(); i++) {
      ObjectNode schedule = (ObjectNode) schedules.get(i);
      if (schedule.path("kinds").toString().contains("APPLICATION")) {
        schedule.put("applicationMode", "ROLLING");
        ((ObjectNode) detail.path("quality"))
            .putArray("heldItems")
            .addObject()
            .put("target", "/schedules/" + i + "/applicationMode");
      }
    }
    assertThat(NoticeProjection.rolling(detail, false)).isFalse();
    assertThat(NoticeProjection.windows(detail, false)).isEmpty();
  }

  @Test
  void 미정_구간을_버리지_않는다() {
    ObjectNode detail =
        (ObjectNode)
            resource("/contracts/examples/extraction.completed.json")
                .path("payload")
                .path("notice");
    for (JsonNode s : detail.path("schedules")) {
      ((ObjectNode) s).putNull("startsAt").putNull("endsAt");
    }
    JsonNode windows = NoticeProjection.windows(detail, false);
    assertThat(windows).hasSize(1);
    assertThat(windows.get(0).path("applyStartOn").isNull()).isTrue();
  }

  @Test
  void 컴파일한_검사기를_동시에_재사용한다() {
    JsonNode event = resource("/notice/extraction-completed-seoripul.json");
    java.util.stream.IntStream.range(0, 32)
        .parallel()
        .forEach(
            i -> assertThatCode(() -> NoticeContract.validate(event)).doesNotThrowAnyException());
  }

  @Test
  void 반복_검증_시간을_측정한다() {
    JsonNode event = resource("/notice/extraction-completed-seoripul.json");
    for (int i = 0; i < 30; i++) NoticeContract.validate(event);
    List<Double> times = new ArrayList<>();
    for (int i = 0; i < 100; i++) {
      long start = System.nanoTime();
      NoticeContract.validate(event);
      times.add((System.nanoTime() - start) / 1_000_000.0);
    }
    Collections.sort(times);
    System.out.printf(
        "NOTICE_CONTRACT_PERF median_ms=%.3f p95_ms=%.3f calls=100%n",
        times.get(50), times.get(94));
  }
}
