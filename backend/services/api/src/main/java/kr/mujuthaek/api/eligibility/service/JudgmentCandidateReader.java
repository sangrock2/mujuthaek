package kr.mujuthaek.api.eligibility.service;

import java.util.List;
import kr.mujuthaek.api.eligibility.model.NoticeCandidate;
import kr.mujuthaek.api.eligibility.rule.Field;
import kr.mujuthaek.api.notice.service.NoticeField;
import kr.mujuthaek.api.notice.service.NoticeQueryService;
import org.springframework.stereotype.Component;

/**
 * 목록 판정 후보를 notice의 판정용 조회로 가져와요. 주거·사업공간은 공고({@link NoticeQueryService#findOpenForJudgment}),
 * 창업지원은 지원사업({@link NoticeQueryService#findOpenProgramsForJudgment})이에요. 창업지원 사업은 모두 정책이라 policy를
 * true로 둬요.
 */
@Component
class JudgmentCandidateReader implements JudgmentCandidates {

  private final NoticeQueryService notices;

  JudgmentCandidateReader(NoticeQueryService notices) {
    this.notices = notices;
  }

  @Override
  public List<NoticeCandidate> openNotices(Field field) {
    return switch (field) {
      case HOUSING -> notices(NoticeField.HOUSING);
      case BUSINESS_SPACE -> notices(NoticeField.BUSINESS_SPACE);
      case STARTUP_SUPPORT -> programs();
    };
  }

  private List<NoticeCandidate> notices(NoticeField field) {
    return notices.findOpenForJudgment(field).stream()
        .map(
            n ->
                new NoticeCandidate(
                    n.noticeId(),
                    n.policy(),
                    n.version(),
                    n.title(),
                    n.applyStart(),
                    n.applyEnd(),
                    n.regionCodes(),
                    n.frame(),
                    n.detailUrl()))
        .toList();
  }

  private List<NoticeCandidate> programs() {
    return notices.findOpenProgramsForJudgment().stream()
        .map(
            p ->
                new NoticeCandidate(
                    p.programId(),
                    true,
                    p.version(),
                    p.title(),
                    p.applyStart(),
                    p.applyEnd(),
                    p.regionCodes(),
                    p.frame(),
                    p.detailUrl()))
        .toList();
  }
}
