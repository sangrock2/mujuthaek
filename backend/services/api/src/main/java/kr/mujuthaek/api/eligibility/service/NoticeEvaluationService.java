package kr.mujuthaek.api.eligibility.service;

import java.util.List;
import java.util.UUID;
import java.util.function.Function;
import kr.mujuthaek.api.eligibility.dto.response.NoticeEvaluationResponse;
import kr.mujuthaek.api.eligibility.rule.Applicant;
import kr.mujuthaek.api.eligibility.rule.IncomeBenchmarks;
import kr.mujuthaek.api.eligibility.rule.Judge;
import kr.mujuthaek.api.eligibility.rule.Overall;
import kr.mujuthaek.api.eligibility.rule.PrepareCost;
import kr.mujuthaek.api.eligibility.service.JudgingFrames.Frame;
import kr.mujuthaek.api.notice.service.NoticeQueryService;
import org.springframework.stereotype.Service;

/**
 * 공고 판정: notice가 가진 판정 틀(extraction이 만든 것)을 판정 입력으로 판정하고, 주택형별 준비할 돈을 계산해요. 입력과 결과는 저장하지 않아요.
 *
 * <p>판정 틀이 없는 공고(검수 대기, 예전에 처리된 공고 등)는 확인 필요로 답해요. 추출이 자격 조건을 다 읽지 못한 공고도 빠진 조건이 있을 수 있어서 지원 가능·지원
 * 불가로 단정하지 않고 확인 필요로 답해요 (목록에서 빠지지 않게).
 */
@Service
public class NoticeEvaluationService {

  static final String NO_FRAME = "이 공고는 아직 자격 판정을 준비하지 못했어요. 공고 원문의 자격 조건을 확인해 주세요";
  static final String PARTIAL_FRAME = "공고의 자격 조건을 다 읽지 못했어요. 공고 원문의 자격 조건을 확인해 주세요";

  private final NoticeQueryService notices;
  private final CriteriaService criteria;
  private final PrepareCostService prepareCost;

  public NoticeEvaluationService(
      NoticeQueryService notices, CriteriaService criteria, PrepareCostService prepareCost) {
    this.notices = notices;
    this.criteria = criteria;
    this.prepareCost = prepareCost;
  }

  public NoticeEvaluationResponse evaluate(UUID noticeId, Applicant applicant) {
    return evaluator(applicant).apply(Frame.of(notices.judgingSource(noticeId)));
  }

  /** 같은 판정 입력으로 공고 여러 개를 판정할 때: 기준 소득·대출 상품은 한 번만 읽어요. */
  public Function<Frame, NoticeEvaluationResponse> evaluator(Applicant applicant) {
    IncomeBenchmarks benchmarks = criteria.benchmarks();
    Function<Long, PrepareCost.Result> prepare = prepareCost.preparer(applicant);
    return source -> evaluate(source, applicant, benchmarks, prepare);
  }

  private static NoticeEvaluationResponse evaluate(
      Frame source,
      Applicant applicant,
      IncomeBenchmarks benchmarks,
      Function<Long, PrepareCost.Result> prepare) {
    Overall overall;
    String reason = null;
    List<Judge.Target> targets = List.of();
    List<String> missing = List.of();
    if (source.judgment() == null) {
      overall = Overall.NEEDS_INPUT;
      reason = NO_FRAME;
    } else {
      Judge.Result result = Judge.evaluate(source.judgment(), applicant, benchmarks);
      overall = result.overall();
      targets = result.targets();
      missing = result.missingInputs();
      if (!source.eligibilityComplete()) {
        // 조건별 결과(충족·불충족)는 그대로 보여 주고, 대상·공고 결과만 확인 필요로
        overall = Overall.NEEDS_INPUT;
        reason = PARTIAL_FRAME;
        targets =
            targets.stream()
                .map(
                    t ->
                        new Judge.Target(
                            t.id(), t.name(), Overall.NEEDS_INPUT, t.summary(), t.items()))
                .toList();
      }
    }
    boolean eligible = overall == Overall.ELIGIBLE;
    var unitTypes =
        source.unitTypes().stream()
            .map(
                u ->
                    new NoticeEvaluationResponse.UnitType(
                        u.houseType(), eligible, prepare.apply(u.depositWon())))
            .toList();
    return new NoticeEvaluationResponse(
        source.noticeId(), overall, reason, targets, missing, unitTypes);
  }
}
