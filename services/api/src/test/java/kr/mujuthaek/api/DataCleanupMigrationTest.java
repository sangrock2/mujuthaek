package kr.mujuthaek.api;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.time.LocalDate;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.annotation.Transactional;

/**
 * 2026-11-10 재검토의 저장된 자료 정리 마이그레이션을 고칠 줄·그대로 둘 줄에 다시 돌려 봐요(앞선 고침은 새로 들어오는 자료에만 적용돼서). 시험이 끝나면 되돌려요.
 */
@SpringBootTest
@Import(TestcontainersConfiguration.class)
@Transactional
class DataCleanupMigrationTest {

  @Autowired JdbcTemplate jdbc;

  @Test
  void applyEndIsClearedOnlyWhenAHeldApplicationScheduleWasLeftOut() throws Exception {
    String held =
        """
        {"schedule":null,
         "applicationWindows":[{"priorityRank":1,"applyStartOn":"2026-10-01","applyEndOn":"2026-10-03"}],
         "notice":{"schedules":[{"id":"r1","kinds":["APPLICATION"]},{"id":"r2","kinds":["APPLICATION"]},
                                {"id":"w","kinds":["WINNER_ANNOUNCEMENT"]}]}}
        """;
    String complete =
        """
        {"schedule":null,
         "applicationWindows":[{"applyStartOn":"2026-10-01","applyEndOn":"2026-10-03"},
                               {"applyStartOn":"2026-10-05","applyEndOn":"2026-10-07"}],
         "notice":{"schedules":[{"id":"r1","kinds":["APPLICATION"]},{"id":"r2","kinds":["APPLICATION"]}]}}
        """;
    String whole =
        """
        {"schedule":{"applyStartOn":"2026-10-01","applyEndOn":"2026-10-03"},
         "applicationWindows":[{"applyStartOn":"2026-10-01","applyEndOn":"2026-10-03"}],
         "notice":{"schedules":[{"id":"r1","kinds":["APPLICATION"]},{"id":"r2","kinds":["APPLICATION"]}]}}
        """;
    UUID heldNotice = notice(held, "2026-10-03");
    UUID completeNotice = notice(complete, "2026-10-07");
    UUID wholeNotice = notice(whole, "2026-10-03");

    run("V202611102310__notice_apply_end_held_application.sql");

    assertThat(applyEnd(heldNotice)).isNull(); // 보류한 2순위가 빠져 앞 마감으로 적혔던 것
    assertThat(applyEnd(completeNotice)).isEqualTo(LocalDate.of(2026, 10, 7));
    assertThat(applyEnd(wholeNotice)).isEqualTo(LocalDate.of(2026, 10, 3)); // 전체 접수 기간이 있으면 그대로
  }

  @Test
  void heldSchedulesAreDroppedOnlyFromFollowUpsSavedTheOldWay() throws Exception {
    String schedules =
        "[{\"id\":\"a\",\"kinds\":[\"APPLICATION\"]},{\"id\":\"b\"},{\"id\":\"c\"},{\"id\":\"d\"}]";
    String heldItems = "[{\"target\":\"/schedules/1\"},{\"target\":\"/schedules/2/endsAt\"}]";
    UUID notice = notice("{}", null);
    UUID old = followUp(notice, schedules, schedules, heldItems);
    UUID already = followUp(notice, "[{\"id\":\"a\"},{\"id\":\"d\"}]", schedules, heldItems);
    UUID nothingHeld = followUp(notice, schedules, schedules, "[]");

    run("V202611102320__notice_follow_up_held_schedules.sql");

    assertThat(ids(old)).isEqualTo("a,d"); // 일정 전체·안의 칸 하나를 보류한 것 모두 빠짐
    assertThat(ids(already)).isEqualTo("a,d"); // 새 규칙으로 저장한 줄은 그대로(차례가 달라 다시 거르지 않음)
    assertThat(ids(nothingHeld)).isEqualTo("a,b,c,d");
  }

  @Test
  void onlyLocationsReusedFromAnotherCityAreRemoved() throws Exception {
    UUID notice = UUID.randomUUID();
    String reused = location(notice, false, "4374510100", "4374010200"); // 증평 주소에 영동 좌표
    String same = location(notice, false, "4374510100", "4374510300");
    String district = location(notice, false, "4111000000", "4111112300"); // 수원시 → 장안구
    String flagged = location(notice, true, "4374510100", "4374010200"); // 경계 밖으로 표시한 것
    String sido = location(notice, false, "4300000000", "4374010200");

    run("V202611102330__area_locations_reused_other_city.sql");

    assertThat(
            jdbc.queryForList(
                "select notice_location_id from area.notice_locations where notice_id = ?",
                String.class,
                notice))
        .containsExactlyInAnyOrder(same, district, flagged, sido)
        .doesNotContain(reused);
  }

  private UUID notice(String payload, String applyEnd) {
    UUID id = UUID.randomUUID();
    jdbc.update(
        "insert into notice.notices (id, raw_post_id, field, title, current_version, apply_end)"
            + " values (?, ?, 'HOUSING', '정리 시험', 1, cast(? as date))",
        id,
        UUID.randomUUID(),
        applyEnd);
    jdbc.update(
        "insert into notice.notice_versions (notice_id, version, raw_post_id, raw_version,"
            + " source_event_id, review_status, payload, conditions, content_hash, created_at)"
            + " values (?, 1, ?, 1, ?, 'AUTO_PASSED', cast(? as jsonb), cast('{}' as jsonb), 'h', now())",
        id,
        UUID.randomUUID(),
        UUID.randomUUID(),
        payload);
    return id;
  }

  private UUID followUp(UUID notice, String saved, String original, String heldItems) {
    UUID rawPost = UUID.randomUUID();
    UUID event = UUID.randomUUID();
    jdbc.update(
        "insert into notice.extraction_results (event_id, raw_post_id, raw_version, review_status,"
            + " outcome, payload, received_at) values (?, ?, 1, 'PARTIALLY_PASSED', 'FOLLOW_UP',"
            + " cast(? as jsonb), now())",
        event,
        rawPost,
        "{\"heldItems\":" + heldItems + ",\"notice\":{\"schedules\":" + original + "}}");
    jdbc.update(
        "insert into notice.notice_follow_ups (raw_post_id, notice_id, original_notice_id,"
            + " raw_version, source_event_id, review_status, title, schedules, content_hash,"
            + " created_at, updated_at) values (?, ?, ?, 1, ?, 'PARTIALLY_PASSED', '후속 안내',"
            + " cast(? as jsonb), 'h', now(), now())",
        rawPost,
        notice,
        notice,
        event,
        saved);
    return rawPost;
  }

  private String location(UUID notice, boolean mismatch, String given, String found) {
    String id = UUID.randomUUID().toString();
    jdbc.update(
        "insert into area.notice_locations (notice_id, notice_location_id, notice_version, kind,"
            + " address_text, bjd_code_given, bjd_code_found, geom, status, region_mismatch)"
            + " values (?, ?, 1, 'COMPLEX', '중앙로 7', ?, ?,"
            + " st_setsrid(st_makepoint(127.5, 36.8), 4326)::geography, 'OK', ?)",
        notice,
        id,
        given,
        found,
        mismatch);
    return id;
  }

  private LocalDate applyEnd(UUID notice) {
    return jdbc.queryForObject(
        "select apply_end from notice.notices where id = ?", LocalDate.class, notice);
  }

  private String ids(UUID followUp) {
    return jdbc.queryForObject(
        "select string_agg(e ->> 'id', ',' order by o) from notice.notice_follow_ups f,"
            + " jsonb_array_elements(f.schedules) with ordinality as x(e, o)"
            + " where f.raw_post_id = ?",
        String.class,
        followUp);
  }

  private void run(String migration) throws Exception {
    try (InputStream in = getClass().getResourceAsStream("/db/migration/" + migration)) {
      jdbc.execute(new String(in.readAllBytes(), StandardCharsets.UTF_8));
    }
  }
}
