package kr.mujuthaek.api.eligibility.rule.frame;

import java.time.LocalDate;
import java.util.List;
import kr.mujuthaek.api.eligibility.rule.Eligibility;
import kr.mujuthaek.api.eligibility.rule.Field;
import kr.mujuthaek.api.eligibility.rule.Verdict;

/**
 * 판정 틀 하나에 대한 판정 결과 (판정 엔진 안쪽). 저장하지 않고, 서비스가 JudgmentResult·MatchResult로 바꿔서 돌려줘요.
 *
 * @param referenceDate 판정에 쓴 기준일 (틀에 기준일이 없으면 판정한 날)
 * @param result 대상군 중 하나라도 충족이면 지원 가능, 충족은 없고 확인 필요가 있으면 확인 필요, 모두 불충족이면 지원 불가
 * @param rank 내 순위: 충족한 대상군 중 가장 앞 신청 순위 (1이 가장 앞). 충족한 대상군에 순위가 없거나 지원 가능이 아니면 null
 * @param common 공통 조건마다의 결과
 * @param groups 대상군마다의 결과 (공통 조건 + 그 대상군 조건)
 * @param preferences 우대마다의 결과 (지원 가능 여부와 상관없어요)
 * @param questions 틀 안의 모든 질문(ASK)과 받은 답. 답하지 않은 질문은 answer가 null
 * @param missingInputs 결과가 확인 필요일 때, 넣으면 결과가 정해질 수 있는 입력
 */
public record FrameJudgment(
    Field field,
    Eligibility result,
    Integer rank,
    LocalDate referenceDate,
    List<Evaluation> common,
    List<GroupResult> groups,
    List<PreferenceResult> preferences,
    List<Frame.Note> notes,
    List<Question> questions,
    List<Input> missingInputs) {

  public FrameJudgment {
    common = List.copyOf(common);
    groups = List.copyOf(groups);
    preferences = List.copyOf(preferences);
    notes = List.copyOf(notes);
    questions = List.copyOf(questions);
    missingInputs = List.copyOf(missingInputs);
  }

  /** 대상군 하나의 결과. criteria에는 그 대상군 조건만 있고, verdict는 공통 조건까지 합친 결과예요. */
  public record GroupResult(Frame.Group group, Verdict verdict, List<Evaluation> criteria) {
    public GroupResult {
      criteria = List.copyOf(criteria);
    }
  }

  /** 우대 하나: MET이면 우대 해당, UNKNOWN이면 우대 확인 필요, NOT_MET이면 해당 없음. */
  public record PreferenceResult(
      Frame.Preference preference, Verdict verdict, List<Evaluation> criteria) {
    public PreferenceResult {
      criteria = List.copyOf(criteria);
    }
  }

  /** 사용자에게 물을 것 (ASK). 답은 요청의 answers에 id로 보내요. */
  public record Question(String id, String text, Answer answer, Purpose purpose) {}

  public enum Purpose {
    /** 자격 질문: 답에 따라 지원 가능 여부가 바뀌어요. */
    ELIGIBILITY,
    /** 우대 질문: 답하지 않아도 지원 가능 여부는 나와요. */
    PREFERENCE
  }
}
