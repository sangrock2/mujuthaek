package kr.mujuthaek.api.eligibility.mapper;

import java.util.Optional;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import kr.mujuthaek.api.eligibility.rule.frame.Answer;
import kr.mujuthaek.api.eligibility.rule.frame.Criterion;
import kr.mujuthaek.api.eligibility.rule.frame.Criterion.Meta;
import kr.mujuthaek.api.eligibility.rule.frame.Criterion.YearsRule;

/**
 * 추출이 업력 조건을 질문으로 준 것(「사업을 시작한 날(법인은 설립등기일)부터 N년 이내인가요?」)을 업력 햇수 조건으로 읽어요.
 *
 * <p>사업공간 틀에는 업력 상한 칸이 없고, K-Startup 「창업 기간」으로 만든 창업지원 틀도 기준일을 몰라 같은 질문으로 줘요 (extraction
 * judgment/policy_frame.py·startup.py가 쓰는 문구 그대로). 사업공간 모집 공고 대부분이 「창업 N년 이내」를 요구해서, 공고마다 묻지 않고 사업
 * 정보의 업력으로 판정해요 (2026-10-29 QA). 문구가 바뀌면 질문으로 남아요 (판정이 틀리지는 않아요).
 */
final class BusinessAgeQuestion {

  private static final Pattern QUESTION =
      Pattern.compile(
          "사업을 시작한 날\\(법인은 설립등기일\\)부터 (\\d{1,3})년"
              + "(?:( 이내인가요)|(이 지나지 않았나요)|( 이상 지났나요)|(이 넘게 지났나요))\\?");

  private BusinessAgeQuestion() {}

  /** 업력 질문이면 업력 햇수 조건, 아니면 빈 값. 답이 「예」일 때 충족인 질문만 바꿔요. */
  static Optional<Criterion.BusinessAgeYears> read(Meta meta, String question, Answer metWhen) {
    if (metWhen != Answer.YES) {
      return Optional.empty();
    }
    Matcher m = QUESTION.matcher(question.strip());
    if (!m.matches()) {
      return Optional.empty();
    }
    int years = Integer.parseInt(m.group(1));
    if (years < 1 || years > 100) {
      return Optional.empty();
    }
    YearsRule rule =
        m.group(2) != null
            ? YearsRule.WITHIN
            : m.group(3) != null
                ? YearsRule.UNDER
                : m.group(4) != null ? YearsRule.AT_LEAST : YearsRule.OVER;
    return Optional.of(new Criterion.BusinessAgeYears(meta, years, rule));
  }
}
