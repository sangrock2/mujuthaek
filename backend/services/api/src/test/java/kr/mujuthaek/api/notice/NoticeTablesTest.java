package kr.mujuthaek.api.notice;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.ArrayList;
import java.util.List;
import kr.mujuthaek.api.TestDatabase;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.ConnectionCallback;
import org.springframework.jdbc.core.JdbcTemplate;

class NoticeTablesTest {

  private final JdbcTemplate jdbc = new JdbcTemplate(TestDatabase.dataSource());

  @Test
  void createsNoticeTables() {
    assertThat(
            jdbc.queryForList(
                "select table_name from information_schema.tables where table_schema = 'notice' order by 1",
                String.class))
        .contains(
            "extraction_results",
            "notice_follow_ups",
            "notice_posts",
            "notice_versions",
            "notices");
  }

  @Test
  void sidoFilterOfNoticeSearchCanUseAnIndex() {
    // NoticeQueries 공고 검색의 시도 필터와 같은 식. 표가 작으면 순차 읽기를 고르니 끄고 봐요
    List<String> plan =
        jdbc.execute(
            (ConnectionCallback<List<String>>)
                c -> {
                  c.setAutoCommit(false);
                  try (var st = c.createStatement()) {
                    st.execute("set local enable_seqscan = off");
                    var rs =
                        st.executeQuery(
                            "explain select 1 from notice.notices n where exists (select 1 from"
                                + " notice.notice_regions r where r.notice_id = n.id and (false or"
                                + " left(r.sigungu_code, 2) in ('11')))");
                    List<String> lines = new ArrayList<>();
                    while (rs.next()) {
                      lines.add(rs.getString(1));
                    }
                    return lines;
                  } finally {
                    c.rollback();
                    c.setAutoCommit(true);
                  }
                });
    assertThat(String.join("\n", plan)).contains("notice_regions_sido_idx");
  }
}
