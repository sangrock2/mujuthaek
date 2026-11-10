package kr.mujuthaek.api.user.service;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import kr.mujuthaek.api.area.service.AreaReportService;
import kr.mujuthaek.api.common.dto.response.MyReportResponse;
import kr.mujuthaek.api.common.text.ScreenPaths;
import kr.mujuthaek.api.notice.service.NoticeQueryService;
import kr.mujuthaek.api.notice.service.NoticeReportQueryService;
import kr.mujuthaek.api.notice.service.NoticeSummary;
import org.springframework.stereotype.Service;

/**
 * 내 정보의 「내 제보」: 공고·혜택·창업지원 사업·일반 제보(notice)와 생활권 제보(area)를 합쳐 최근 것부터. 제보는 하루 20건까지라 최근 {@value
 * #LIMIT}건만 보여 줘요.
 */
@Service
public class MyReportService {

  static final int LIMIT = 100;

  private final NoticeReportQueryService noticeReports;
  private final AreaReportService areaReports;
  private final NoticeQueryService notices;

  public MyReportService(
      NoticeReportQueryService noticeReports,
      AreaReportService areaReports,
      NoticeQueryService notices) {
    this.noticeReports = noticeReports;
    this.areaReports = areaReports;
    this.notices = notices;
  }

  public List<MyReportResponse> mine(UUID userId) {
    List<MyReportResponse> area = areaReports.mine(userId, LIMIT);
    // 생활권 제보는 공고 제목·화면을 공고 쪽에서 채워요 (합쳐진 공고는 남은 공고로)
    Map<UUID, NoticeSummary> summaries =
        notices.findSummaries(area.stream().map(MyReportResponse::targetId).toList());
    List<MyReportResponse> all = new ArrayList<>(noticeReports.mine(userId, LIMIT));
    for (MyReportResponse r : area) {
      NoticeSummary n = summaries.get(r.targetId());
      all.add(
          n == null
              ? r
              : new MyReportResponse(
                  r.id(),
                  r.kind(),
                  n.noticeId(),
                  n.title(),
                  r.field(),
                  r.reportedValue(),
                  r.note(),
                  r.status(),
                  r.result(),
                  r.reply(),
                  r.createdAt(),
                  r.handledAt(),
                  ScreenPaths.notice(n.noticeId(), n.field())));
    }
    all.sort(Comparator.comparing(MyReportResponse::createdAt).reversed());
    return all.size() > LIMIT ? all.subList(0, LIMIT) : all;
  }
}
