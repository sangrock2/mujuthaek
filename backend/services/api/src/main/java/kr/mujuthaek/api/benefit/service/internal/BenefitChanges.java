package kr.mujuthaek.api.benefit.service.internal;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Objects;
import kr.mujuthaek.api.benefit.mapper.PolicyExtractedEvent;
import kr.mujuthaek.api.benefit.repository.BenefitRepository.Row;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

/**
 * 저장된 혜택과 새 버전을 비교해 사용자가 볼 내용 중 바뀐 부분의 이름을 골라요 (BenefitUpdated.changedFields).
 *
 * <p>AI가 쓰는 글(요약·신청 방법·일정 설명·근거 문장·원문 글자)과 신뢰도는 비교하지 않아요. 같은 정책을 다시 추출하면 글자만 조금 바뀌는데, 그때마다 정정 알림이
 * 가면 안 돼서요. 구조 값(날짜·금액·조건 값·서류 목록)만 봐요.
 */
final class BenefitChanges {

  static final String BASIC = "basic";
  static final String REGION = "region";
  static final String SCHEDULE = "schedule";
  static final String SUPPORTS = "supports";
  static final String CONDITIONS = "conditions";
  static final String APPLICATION = "application";

  private BenefitChanges() {}

  /** 바뀐 부분 이름 (정해진 순서). 없으면 빈 목록 */
  static List<String> between(Row saved, PolicyExtractedEvent next, JsonMapper json) {
    List<String> changed = new ArrayList<>();
    if (!Objects.equals(saved.title(), next.title())
        || !Objects.equals(saved.agency(), next.agency())) {
      changed.add(BASIC);
    }
    if (!Objects.equals(saved.regionScope(), next.regionScope())
        || !new HashSet<>(saved.regionCodes()).equals(new HashSet<>(next.regionCodes()))) {
      changed.add(REGION);
    }
    if (!Objects.equals(saved.applyStart(), next.applyStart())
        || !Objects.equals(saved.applyEnd(), next.applyEnd())
        || saved.applyAlways() != next.applyAlways()
        || !Objects.equals(saved.businessStart(), next.businessStart())
        || !Objects.equals(saved.businessEnd(), next.businessEnd())) {
      changed.add(SCHEDULE);
    }
    if (!sameSupports(saved.supports(), next.supports())) {
      changed.add(SUPPORTS);
    }
    if (!sameConditions(saved.conditions(), next.conditions(), json)) {
      changed.add(CONDITIONS);
    }
    if (!Objects.equals(saved.documents(), next.documents())
        || !Objects.equals(saved.contact(), next.contact())
        || !Objects.equals(saved.applyUrl(), next.applyUrl())) {
      changed.add(APPLICATION);
    }
    return changed;
  }

  private static boolean sameSupports(
      List<PolicyExtractedEvent.Support> saved, List<PolicyExtractedEvent.Support> next) {
    if (saved.size() != next.size()) {
      return false;
    }
    for (int i = 0; i < saved.size(); i++) {
      var a = saved.get(i);
      var b = next.get(i);
      if (!Objects.equals(a.kind(), b.kind())
          || !Objects.equals(a.amountMax(), b.amountMax())
          || !Objects.equals(a.amountPer(), b.amountPer())
          || !Objects.equals(a.months(), b.months())
          || !sameNumber(a.ratePct(), b.ratePct())) {
        return false;
      }
    }
    return true;
  }

  private static boolean sameConditions(
      List<PolicyExtractedEvent.Condition> saved,
      List<PolicyExtractedEvent.Condition> next,
      JsonMapper json) {
    if (saved.size() != next.size()) {
      return false;
    }
    for (int i = 0; i < saved.size(); i++) {
      var a = saved.get(i);
      var b = next.get(i);
      if (!Objects.equals(a.type(), b.type())
          || a.group() != b.group()
          || a.known() != b.known()
          || !Objects.equals(value(a.valueJson(), json), value(b.valueJson(), json))) {
        return false;
      }
    }
    return true;
  }

  /** DB(jsonb)는 칸 순서·띄어쓰기를 바꿔서 글자 대신 JSON으로 비교해요 */
  private static JsonNode value(String valueJson, JsonMapper json) {
    return valueJson == null ? null : json.readTree(valueJson);
  }

  /** 3.5와 3.50은 같아요 (DB numeric은 자릿수를 붙여 돌려줘요) */
  private static boolean sameNumber(BigDecimal a, BigDecimal b) {
    return a == null ? b == null : b != null && a.compareTo(b) == 0;
  }
}
