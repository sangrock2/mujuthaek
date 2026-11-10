package kr.mujuthaek.api.notice.mapper;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.UUID;
import java.util.function.Consumer;
import kr.mujuthaek.api.notice.NoticeFixtures;
import kr.mujuthaek.api.notice.dto.response.NoticeDetailResponse;
import kr.mujuthaek.api.notice.dto.response.NoticeDetailResponse.ApplicationEmail;
import kr.mujuthaek.api.notice.dto.response.NoticeDetailResponse.Place;
import kr.mujuthaek.api.notice.dto.response.NoticeDetailResponse.RequiredDocument;
import kr.mujuthaek.api.notice.dto.response.NoticeDetailResponse.TimeRange;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.node.ArrayNode;
import tools.jackson.databind.node.ObjectNode;

/** 일정의 접수 방법·장소·시각과 제출 서류 묶음 (프론트 요청 2026-10-23). */
class NoticeDetailMapperScheduleTest {

  private static NoticeDetailResponse map(Consumer<ObjectNode> change) {
    ObjectNode p = NoticeFixtures.payload(UUID.randomUUID(), 1);
    change.accept((ObjectNode) p.get("notice"));
    return NoticeDetailMapper.map(
        null,
        p,
        List.of(),
        List.of(),
        1,
        false,
        OffsetDateTime.parse("2026-10-22T09:00:00+09:00"),
        LocalDate.of(2026, 10, 22));
  }

  private static ObjectNode schedule(ObjectNode notice) {
    return (ObjectNode) notice.get("schedules").get(0);
  }

  @Test
  void 일정의_접수_장소_시각_제외_요일_신청_방법을_보여준다() {
    NoticeDetailResponse detail =
        map(
            n -> {
              ObjectNode s = schedule(n);
              s.putArray("channels").add("ONLINE").add("ONSITE");
              s.putArray("places")
                  .addObject()
                  .put("name", "가상주거공사 1층 접수처")
                  .put("address", "서울특별시 종로구 가상로 1")
                  .putNull("detail");
              s.putObject("applicationEmail")
                  .put("address", "apply@example.org")
                  .put("subjectFormat", "[신청] 성명_주택형");
              s.putArray("dailyHours").addObject().put("start", "10:00").put("end", "18:00");
              s.putArray("breaks").addObject().put("start", "12:00").put("end", "13:00");
              s.putArray("excludedDays").add("SAT").add("SUN").add("HOLIDAY");
              s.put("timeNote", "마감일은 16시까지예요.");
              ((ObjectNode) n.get("notice"))
                  .putArray("applicationChannels")
                  .add("ONLINE")
                  .add("ONSITE");
            });

    NoticeDetailResponse.Schedule s = detail.schedules().getFirst();
    assertThat(s.channels()).containsExactly("ONLINE", "ONSITE");
    assertThat(s.places()).containsExactly(new Place("가상주거공사 1층 접수처", "서울특별시 종로구 가상로 1", null));
    assertThat(s.applicationEmail())
        .isEqualTo(new ApplicationEmail("apply@example.org", "[신청] 성명_주택형"));
    assertThat(s.dailyHours()).containsExactly(new TimeRange("10:00", "18:00"));
    assertThat(s.breaks()).containsExactly(new TimeRange("12:00", "13:00"));
    assertThat(s.excludedDays()).containsExactly("SAT", "SUN", "HOLIDAY");
    assertThat(s.timeNote()).isEqualTo("마감일은 16시까지예요.");
    assertThat(detail.summary().applicationChannels()).containsExactly("ONLINE", "ONSITE");
  }

  @Test
  void 이전_저장본은_새_칸이_비고_자유_글자_신청_방법은_빼고_공고_신청_방법은_일정에서_계산한다() {
    NoticeDetailResponse detail =
        map(
            n -> {
              ObjectNode s = schedule(n);
              for (String key :
                  List.of(
                      "places",
                      "applicationEmail",
                      "dailyHours",
                      "breaks",
                      "excludedDays",
                      "timeNote")) {
                s.remove(key);
              }
              s.putArray("channels").add("인터넷").add("ONLINE");
              ((ObjectNode) n.get("notice")).remove("applicationChannels");
            });

    NoticeDetailResponse.Schedule s = detail.schedules().getFirst();
    assertThat(s.channels()).containsExactly("ONLINE");
    assertThat(s.places()).isEmpty();
    assertThat(s.applicationEmail()).isNull();
    assertThat(s.dailyHours()).isEmpty();
    assertThat(s.excludedDays()).isEmpty();
    assertThat(s.timeNote()).isNull();
    assertThat(detail.summary().applicationChannels()).containsExactly("ONLINE");
  }

  @Test
  void 제출_서류는_묶음_순서로_보여주고_보류한_서류는_뺀다() {
    NoticeDetailResponse detail =
        map(
            n -> {
              ArrayNode documents = (ArrayNode) n.get("requiredDocuments");
              ObjectNode first = (ObjectNode) documents.get(0);
              first.put("group", "PROXY_SPOUSE").put("copies", 1).put("issuer", "주민센터");
              documents
                  .addObject()
                  .setAll(first.deepCopy())
                  .put("id", "doc-common")
                  .put("group", "COMMON");
              documents.addObject().setAll(first.deepCopy()).put("id", "doc-none").putNull("group");
              documents
                  .addObject()
                  .setAll(first.deepCopy())
                  .put("id", "doc-held")
                  .put("group", "COMMON");
              ((ObjectNode) n.get("quality"))
                  .putArray("heldItems")
                  .addObject()
                  .put("target", "/requiredDocuments/3")
                  .put("description", "원문 확인 필요");
            });

    assertThat(detail.requiredDocuments())
        .extracting(RequiredDocument::id, RequiredDocument::group)
        .containsExactly(
            org.assertj.core.groups.Tuple.tuple("doc-common", "COMMON"),
            org.assertj.core.groups.Tuple.tuple(
                detail.requiredDocuments().get(1).id(), "PROXY_SPOUSE"),
            org.assertj.core.groups.Tuple.tuple("doc-none", null));
    RequiredDocument proxy = detail.requiredDocuments().get(1);
    assertThat(proxy.copies()).isEqualTo(1);
    assertThat(proxy.issuer()).isEqualTo("주민센터");
    assertThat(proxy.evidence()).isNotEmpty();
    assertThat(detail.heldItems())
        .extracting(NoticeDetailResponse.HeldItem::section)
        .containsExactly("requiredDocuments");
  }

  @Test
  void 보류한_일정은_빠진다() {
    NoticeDetailResponse detail =
        map(
            n -> {
              schedule(n).putArray("kinds").add("VIEWING");
              ((ObjectNode) n.get("quality"))
                  .putArray("heldItems")
                  .addObject()
                  .put("target", "/schedules/0")
                  .put("description", "형식이 맞지 않아 원문 확인 필요");
            });

    assertThat(detail.schedules()).isEmpty();
    assertThat(detail.heldItems())
        .extracting(NoticeDetailResponse.HeldItem::target)
        .containsExactly("/schedules/0");
  }
}
