package kr.mujuthaek.api.eligibility.mapper;

import java.util.List;
import kr.mujuthaek.api.eligibility.model.JudgmentResult;
import kr.mujuthaek.api.eligibility.model.MissingInput;
import kr.mujuthaek.api.eligibility.rule.Eligibility;
import kr.mujuthaek.api.eligibility.rule.Verdict;
import kr.mujuthaek.api.eligibility.rule.frame.Evaluation;
import kr.mujuthaek.api.eligibility.rule.frame.FrameJudgment;
import kr.mujuthaek.api.eligibility.rule.frame.Input;

/** 판정 엔진 결과 → 정제된 판정 결과 (판정 서비스가 불러요). */
public final class JudgmentMapper {

  private JudgmentMapper() {}

  public static JudgmentResult toResult(FrameJudgment j) {
    return new JudgmentResult(
        j.field().name(),
        j.result(),
        j.rank(),
        j.referenceDate(),
        criteria(j.common()),
        j.groups().stream()
            .map(
                g ->
                    new JudgmentResult.Group(
                        g.group().id(),
                        g.group().name(),
                        g.group().rank(),
                        Eligibility.of(g.verdict()),
                        criteria(g.criteria())))
            .toList(),
        j.preferences().stream()
            .map(
                p ->
                    new JudgmentResult.Preference(
                        p.preference().id(),
                        p.preference().label(),
                        p.preference().groupId(),
                        p.preference().effect().name(),
                        p.preference().points(),
                        p.verdict(),
                        criteria(p.criteria())))
            .toList(),
        j.notes().stream()
            .map(
                n ->
                    new JudgmentResult.Note(
                        n.kind().name(), n.groupId(), n.text(), n.quote(), n.page()))
            .toList(),
        missingInputs(j.missingInputs()));
  }

  static List<MissingInput> missingInputs(List<Input> inputs) {
    return inputs.stream().map(i -> new MissingInput(i.field(), i.label())).toList();
  }

  private static List<JudgmentResult.Criterion> criteria(List<Evaluation> evaluations) {
    return evaluations.stream().map(JudgmentMapper::criterion).toList();
  }

  private static JudgmentResult.Criterion criterion(Evaluation e) {
    return new JudgmentResult.Criterion(
        e.criterion().id(),
        e.criterion().kind(),
        e.verdict(),
        e.summary(),
        e.reason(),
        e.verdict() == Verdict.UNKNOWN
            ? e.missing().stream().map(Input::field).toList()
            : List.of(),
        e.criterion().meta().quote(),
        e.criterion().meta().page(),
        e.options().stream()
            .map(o -> new JudgmentResult.Option(o.label(), o.verdict(), criteria(o.criteria())))
            .toList());
  }
}
