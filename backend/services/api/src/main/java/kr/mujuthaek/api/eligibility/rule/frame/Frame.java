package kr.mujuthaek.api.eligibility.rule.frame;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.List;
import kr.mujuthaek.api.eligibility.rule.Field;

/**
 * 판정 틀 하나 (공고 한 건·한 버전). 추출 결과를 판정용으로 한 번 더 가공한 데이터예요.
 *
 * @param sourceId 가공한 공고 (주거·사업공간은 rawPostId, 창업지원은 rawPolicyId)
 * @param referenceDate 판정 기준일 (보통 모집공고일). 조건에 asOf가 있으면 그 조건은 asOf로 계산해요. 창업지원 틀은 공고에 기준일 문구가 없으면
 *     null이고, 그러면 판정하는 날 기준이에요
 * @param common 모든 대상군에 공통인 조건
 * @param groups 대상군 (최소 1개). 대상군 하나 = 공통 조건 + 그 대상군 조건
 * @param preferences 우대 (자격이 아니라 표시용). 주거 틀에는 없어요
 * @param notes 판정하지 않고 보여만 줄 문장
 */
public record Frame(
    Field field,
    String sourceId,
    int sourceVersion,
    LocalDate referenceDate,
    List<Criterion> common,
    List<Group> groups,
    List<Preference> preferences,
    List<Note> notes) {

  public Frame {
    common = List.copyOf(common);
    groups = List.copyOf(groups);
    preferences = List.copyOf(preferences);
    notes = List.copyOf(notes);
  }

  /**
   * 대상군 (공급 유형·신청 대상·신청 분야·신청 순위).
   *
   * @param rank 공고가 정한 신청 순위 (1이 가장 앞). 순위가 없는 대상군은 null
   */
  public record Group(String id, String name, Integer rank, List<Criterion> criteria) {
    public Group {
      criteria = List.copyOf(criteria);
    }
  }

  /**
   * 우대: 가점·우선 선정·평가 면제. 안 조건을 모두 충족하면 '우대 해당'으로 표시하고, 지원 가능 여부는 바꾸지 않아요.
   *
   * @param groupId 특정 대상군에만 해당하면 그 ID, 아니면 null
   * @param points 가점이면 점수 (적혀 있지 않으면 null)
   */
  public record Preference(
      String id,
      String label,
      String groupId,
      Effect effect,
      BigDecimal points,
      List<Criterion> criteria,
      String quote,
      Integer page) {

    public Preference {
      criteria = List.copyOf(criteria);
    }

    public enum Effect {
      /** 우선 선정·우대 (점수 없음). */
      PRIORITY,
      /** 평가 가점. */
      BONUS_POINTS,
      /** 평가 면제 같은 그 밖의 우대. */
      OTHER
    }
  }

  /** 판정하지 않고 화면에 안내로만 보여줄 문장. */
  public record Note(Kind kind, String groupId, String text, String quote, Integer page) {

    public enum Kind {
      /** 신청 규칙 (1세대 1주택, 공동명의 불허 …). */
      RULE,
      /** 당첨·계약·입주 뒤 할 일. */
      OBLIGATION,
      /** 선정 방식·순위·평가. */
      SELECTION,
      OTHER
    }
  }
}
